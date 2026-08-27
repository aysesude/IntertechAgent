import {
  ApiError,
  UnauthorizedError,
  getAccessToken,
  getApiBaseUrl,
  isApiConfigured,
  notifyUnauthorized,
} from "./client";

/**
 * `POST /api/chat` — sunucu yanıtı SSE (`text/event-stream`) olarak akıtır.
 *
 * NEDEN `EventSource` KULLANILMIYOR: tarayıcının yerleşik EventSource'u
 * yalnızca GET destekler ve başlık eklenemez; bizim isteğimiz hem POST gövdesi
 * hem de `Authorization` başlığı taşıyor. Bu yüzden `fetch` + `ReadableStream`
 * üzerinden çerçeveler elle ayrıştırılıyor.
 *
 * Olay sırası: `session` → `token` × N → `done`. Hata olursa `done` yerine
 * `error` gelir.
 */

export interface ChatRequest {
  user_id: string;
  session_id: string | null;
  message: string;
}

export interface ChatSessionEvent {
  session_id: string;
}

export interface ChatTokenEvent {
  delta: string;
}

export interface ChatDoneEvent {
  agent: string | null;
  final_answer: string;
  /** Ajanın kullandığı yapısal veri (ör. portföy özeti). Şimdilik gösterilmiyor. */
  data: unknown;
}

export interface ChatErrorEvent {
  message: string;
}

export interface ChatStreamHandlers {
  onSession?: (event: ChatSessionEvent) => void;
  onToken?: (event: ChatTokenEvent) => void;
  onDone?: (event: ChatDoneEvent) => void;
  onError?: (event: ChatErrorEvent) => void;
}

/**
 * Gelen metin parçalarını biriktirip tamamlanmış SSE çerçevelerini işler.
 *
 * AYRI VE SAF TUTULDU çünkü kırılgan olan kısım burası ve tarayıcıda ancak
 * şansa bağlı olarak hata verir: bir çerçeve iki ağ paketine bölünebilir,
 * tek pakette birden fazla olay gelebilir, ayraç CRLF olabilir. Ağ katmanından
 * bağımsız olduğu için bunların hepsi testte deterministik olarak sınanabiliyor
 * (bkz. chat.test.ts).
 */
export function createSseParser(handlers: ChatStreamHandlers) {
  let buffer = "";

  function dispatch(rawFrame: string): void {
    let eventName = "message";
    // Bir çerçevede birden çok `data:` satırı olabilir (SSE'de çok satırlı
    // veri böyle taşınır); satır sonlarıyla birleştirilir.
    const dataLines: string[] = [];

    for (const line of rawFrame.split("\n")) {
      if (line.startsWith(":")) continue; // yorum satırı / canlı tutma sinyali
      if (line.startsWith("event:")) {
        eventName = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trim());
      }
    }

    if (dataLines.length === 0) return;

    let data: unknown;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      // Bozuk bir çerçeve yüzünden tüm akışı düşürmüyoruz: sonraki
      // çerçeveler hâlâ işlenebilir.
      return;
    }

    switch (eventName) {
      case "session":
        handlers.onSession?.(data as ChatSessionEvent);
        break;
      case "token":
        handlers.onToken?.(data as ChatTokenEvent);
        break;
      case "done":
        handlers.onDone?.(data as ChatDoneEvent);
        break;
      case "error":
        handlers.onError?.(data as ChatErrorEvent);
        break;
    }
  }

  return {
    /** Akıştan gelen bir metin parçasını işler. Tamamlanmamış kuyruk saklanır. */
    push(chunk: string): void {
      // sse-starlette çerçeveleri CRLF ile ayırıyor; tek biçime indiriyoruz.
      buffer += chunk.replace(/\r\n/g, "\n");

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        dispatch(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    },
  };
}

export async function streamChat(
  request: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  if (!isApiConfigured) {
    throw new ApiError("VITE_API_BASE_URL tanımlı değil");
  }

  const token = getAccessToken();
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Sunucuya ulaşılamadı.");
  }

  if (!response.ok) {
    // Hata gövdesi JSON: {"detail": "..."} — metin Türkçe ve kullanıcıya
    // gösterilebilir halde (bkz. backend/app/api/chat.py).
    let detail: string | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : null;
    } catch {
      /* gövde okunamadı, aşağıdaki yedek metin kullanılır */
    }

    if (response.status === 401) {
      // Oturum düşmüş: AuthProvider'ı haberdar et ki kullanıcı boş bir
      // sohbet ekranına değil giriş ekranına düşsün.
      notifyUnauthorized();
      throw new UnauthorizedError(detail ?? undefined);
    }
    throw new ApiError(detail ?? `Sohbet başlatılamadı: ${response.status}`, response.status);
  }

  if (!response.body) {
    throw new ApiError("Sunucu akış döndürmedi.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser(handlers);

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
  } finally {
    // Kullanıcı sayfadan ayrıldığında ya da yeni mesaj gönderdiğinde okuyucu
    // serbest bırakılmazsa bağlantı açık kalır.
    reader.releaseLock();
  }
}
