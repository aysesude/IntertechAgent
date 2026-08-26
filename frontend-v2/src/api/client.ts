/**
 * Tipli fetch katmanı.
 *
 * Token bu modülde bir modül değişkeninde tutulur, React context'inde değil:
 * `apiFetch` bir React bileşeni değildir ve context okuyamaz. AuthContext,
 * durumu değiştikçe `setAccessToken` ile burayı günceller — tek yönlü, döngüsel
 * bağımlılık yok.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export const isApiConfigured = API_BASE_URL.length > 0;

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** 401 — kimlik yok/geçersiz. Yapılacak şey: yeniden giriş. */
export class UnauthorizedError extends ApiError {
  constructor(message = "Oturumunuz sona erdi, lütfen tekrar giriş yapın.") {
    super(message, 401);
    this.name = "UnauthorizedError";
  }
}

/** 403 — kimlik geçerli ama bu veri başkasının (AK 5.4). Yeniden giriş çözmez. */
export class ForbiddenError extends ApiError {
  constructor(message = "Bu veriye erişim yetkiniz yok.") {
    super(message, 403);
    this.name = "ForbiddenError";
  }
}

let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/**
 * Token süresi dolduğunda çağrılacak fonksiyon (AuthContext oturumu kapatır).
 * Kayıt edilmezse 401 yalnızca hata olarak yükselir.
 */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/**
 * Akıtılan (streaming) sohbet isteği JSON gövdesi değil ham bir okuma akışı
 * döndürdüğü için `apiFetch`'ten geçemiyor ve kendi `fetch`'ini kuruyor
 * (bkz. api/chat.ts). Taban adresi, token'ı ve 401 işleyicisini oradan da
 * kullanabilmek için üçü burada dışa açılıyor — kopyalanmasınlar diye.
 */
export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function notifyUnauthorized(): void {
  unauthorizedHandler?.();
}

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
  /** 204 gibi gövdesiz yanıtlarda JSON çözme adımı atlanır. */
  parseJson?: boolean;
  /**
   * Giriş isteği için: yanlış şifrede gelen 401, "oturum düştü" demek
   * değildir — oturum zaten yok. Bu bayrak olmadan giriş denemesi
   * AuthContext'i gereksizce sıfırlardı.
   */
  skipUnauthorizedHandler?: boolean;
}

/**
 * Backend hatayı `{"detail": "..."}` ile döner ve bu metin TÜRKÇE, kullanıcıya
 * gösterilebilir haldedir (bkz. backend/app/api/*). Ham "HTTP 401" yerine onu
 * kullanıyoruz; okunamazsa duruma göre anlamlı bir yedek metin üretiyoruz.
 */
async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!isApiConfigured) {
    throw new ApiError("VITE_API_BASE_URL tanımlı değil");
  }

  const {
    timeoutMs = 8000,
    skipUnauthorizedHandler = false,
    parseJson = true,
    headers,
    ...rest
  } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...headers,
      },
    });

    if (!response.ok) {
      const detail = await readErrorDetail(response);
      if (response.status === 401) {
        if (!skipUnauthorizedHandler) unauthorizedHandler?.();
        throw new UnauthorizedError(detail ?? undefined);
      }
      if (response.status === 403) {
        throw new ForbiddenError(detail ?? undefined);
      }
      throw new ApiError(detail ?? `API isteği başarısız: ${response.status}`, response.status);
    }

    if (!parseJson) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    // AbortController zaman aşımı DOMException("AbortError") fırlatıyor;
    // kullanıcıya "signal is aborted" göstermek anlamsız.
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Sunucu zamanında yanıt vermedi.");
    }
    if (error instanceof ApiError) throw error;
    // Ağ hatası (sunucu kapalı, CORS, DNS) — fetch burada TypeError fırlatır.
    throw new ApiError("Sunucuya ulaşılamadı.");
  } finally {
    clearTimeout(timer);
  }
}

export function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: "GET" });
}

export function apiPost<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: "POST", body: JSON.stringify(body) });
}

/**
 * Gövdesiz yanıt döndüren (204) uçlar için.
 *
 * `apiPost` her zaman JSON çözmeye çalışıyor; 204'te gövde olmadığı için
 * bu bir ayrıştırma hatasına dönüşür ve başarılı istek başarısız görünürdü.
 */
export function apiPostNoContent(
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<void> {
  return apiFetch<void>(path, {
    ...options,
    method: "POST",
    body: JSON.stringify(body),
    parseJson: false,
  });
}
