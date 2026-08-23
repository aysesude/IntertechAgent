import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * SSE okuyucusunun testleri.
 *
 * Buradaki kırılganlık ağ katmanından geliyor ve tarayıcıda ancak ŞANSA BAĞLI
 * olarak ortaya çıkıyor: bir çerçeve iki pakete bölünebilir, tek pakette
 * birden fazla olay gelebilir, ayraç CRLF olabilir. Elle denerken bunlar
 * genelde "çalışıyor" görünür; testte deterministik olarak zorlanabiliyor.
 */

const notifyUnauthorized = vi.fn();

vi.mock("./client", async () => {
  const gercek = await vi.importActual<typeof import("./client")>("./client");
  return {
    ...gercek,
    isApiConfigured: true,
    getApiBaseUrl: () => "https://ornek.test",
    getAccessToken: () => "test-token",
    notifyUnauthorized: (...args: unknown[]) => notifyUnauthorized(...args),
  };
});

const { createSseParser, streamChat } = await import("./chat");
const { UnauthorizedError } = await import("./client");

function toplayici() {
  const olaylar: string[] = [];
  const tokenlar: string[] = [];
  return {
    olaylar,
    tokenlar,
    handlers: {
      onSession: (e: { session_id: string }) => olaylar.push(`session:${e.session_id}`),
      onToken: (e: { delta: string }) => {
        tokenlar.push(e.delta);
        olaylar.push(`token:${e.delta}`);
      },
      onDone: (e: { final_answer: string }) => olaylar.push(`done:${e.final_answer}`),
      onError: (e: { message: string }) => olaylar.push(`error:${e.message}`),
    },
  };
}

describe("createSseParser", () => {
  it("tek parçada gelen tam bir akışı sırayla işler", () => {
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push(
      'event: session\ndata: {"session_id":"s1"}\n\n' +
        'event: token\ndata: {"delta":"Merhaba"}\n\n' +
        'event: done\ndata: {"agent":"portfolio_agent","final_answer":"Merhaba","data":null}\n\n',
    );

    expect(t.olaylar).toEqual(["session:s1", "token:Merhaba", "done:Merhaba"]);
  });

  it("ÇERÇEVE ORTASINDAN bölünmüş parçaları birleştirir", () => {
    // Ağ paketleri çerçeve sınırlarına saygı duymaz. Tampon olmasaydı bu
    // durumda hiçbir olay işlenmezdi.
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push('event: tok');
    parser.push('en\ndata: {"del');
    parser.push('ta":"par');
    parser.push('ça"}\n\n');

    expect(t.tokenlar).toEqual(["parça"]);
  });

  it("CRLF ayraçlı çerçeveleri de anlar", () => {
    // sse-starlette çerçeveleri \r\n ile ayırıyor.
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push('event: token\r\ndata: {"delta":"crlf"}\r\n\r\n');

    expect(t.tokenlar).toEqual(["crlf"]);
  });

  it("tek parçadaki çok sayıda token'ın SIRASINI korur", () => {
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push(
      'event: token\ndata: {"delta":"Port"}\n\n' +
        'event: token\ndata: {"delta":"föyünüz"}\n\n' +
        'event: token\ndata: {"delta":" iyi"}\n\n',
    );

    // Sıra bozulursa cevap anlamsız bir kelime salatasına döner.
    expect(t.tokenlar.join("")).toBe("Portföyünüz iyi");
  });

  it("bozuk bir çerçeve akışın geri kalanını düşürmez", () => {
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push("event: token\ndata: {bozuk json\n\n");
    parser.push('event: token\ndata: {"delta":"sağlam"}\n\n');

    expect(t.tokenlar).toEqual(["sağlam"]);
  });

  it("yorum satırlarını ve boş çerçeveleri yok sayar", () => {
    // SSE'de ':' ile başlayan satırlar canlı tutma sinyalidir.
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push(": canli tutma\n\n");
    parser.push('event: token\ndata: {"delta":"x"}\n\n');

    expect(t.olaylar).toEqual(["token:x"]);
  });

  it("tamamlanmamış son çerçeveyi İŞLEMEZ", () => {
    // Akış yarıda kesilirse eksik veri gösterilmemeli.
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push('event: token\ndata: {"delta":"yarim"}');

    expect(t.olaylar).toEqual([]);
  });

  it("hata olayını iletir", () => {
    const t = toplayici();
    const parser = createSseParser(t.handlers);

    parser.push('event: error\ndata: {"message":"Ajan yanıt veremedi"}\n\n');

    expect(t.olaylar).toEqual(["error:Ajan yanıt veremedi"]);
  });
});

// ---------------------------------------------------------------------------

function akisYanitiVer(parcalar: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const parca of parcalar) controller.enqueue(encoder.encode(parca));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe("streamChat", () => {
  beforeEach(() => {
    notifyUnauthorized.mockReset();
    vi.unstubAllGlobals();
  });

  it("Authorization başlığını ve gövdeyi doğru gönderir", async () => {
    const fetchSahte = vi.fn().mockResolvedValue(
      akisYanitiVer(['event: done\ndata: {"agent":null,"final_answer":"ok","data":null}\n\n']),
    );
    vi.stubGlobal("fetch", fetchSahte);

    const t = toplayici();
    await streamChat(
      { user_id: "u1", session_id: null, message: "Portföyüm nasıl?" },
      t.handlers,
    );

    const [url, init] = fetchSahte.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://ornek.test/api/chat");
    expect(init.method).toBe("POST");
    // Kimlik doğrulama geldikten sonra bu başlık olmadan uç 401 döner.
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
    expect(JSON.parse(init.body as string)).toEqual({
      user_id: "u1",
      session_id: null,
      message: "Portföyüm nasıl?",
    });
  });

  it("akış boyunca olayları sırayla iletir", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        akisYanitiVer([
          'event: session\ndata: {"session_id":"s9"}\n\n',
          'event: token\ndata: {"delta":"Merhaba "}\n\n',
          'event: token\ndata: {"delta":"dünya"}\n\n',
          'event: done\ndata: {"agent":"portfolio_agent","final_answer":"Merhaba dünya","data":null}\n\n',
        ]),
      ),
    );

    const t = toplayici();
    await streamChat({ user_id: "u1", session_id: null, message: "selam" }, t.handlers);

    expect(t.olaylar).toEqual([
      "session:s9",
      "token:Merhaba ",
      "token:dünya",
      "done:Merhaba dünya",
    ]);
  });

  it("401'de oturumu düşürür ve UnauthorizedError fırlatır", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Oturumunuz sona erdi." }), { status: 401 }),
      ),
    );

    const t = toplayici();
    await expect(
      streamChat({ user_id: "u1", session_id: null, message: "selam" }, t.handlers),
    ).rejects.toBeInstanceOf(UnauthorizedError);

    // Kullanıcı boş bir sohbet ekranında kalmasın, giriş ekranına düşsün.
    expect(notifyUnauthorized).toHaveBeenCalled();
  });

  it("403'te sunucunun Türkçe mesajını taşır", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Bu veriye erişim yetkiniz yok." }), { status: 403 }),
      ),
    );

    const t = toplayici();
    await expect(
      streamChat({ user_id: "baskasi", session_id: null, message: "selam" }, t.handlers),
    ).rejects.toThrow("Bu veriye erişim yetkiniz yok.");
    expect(notifyUnauthorized).not.toHaveBeenCalled();
  });

  it("ağ hatasında anlaşılır bir mesaj verir", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const t = toplayici();
    await expect(
      streamChat({ user_id: "u1", session_id: null, message: "selam" }, t.handlers),
    ).rejects.toThrow("Sunucuya ulaşılamadı.");
  });

  it("iptal edildiğinde AbortError'ı yutmaz", async () => {
    // Sayfa değişince ya da yeni mesaj gönderilince akış iptal ediliyor;
    // bunun ağ hatasıyla karıştırılmaması gerekiyor.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")),
    );

    const t = toplayici();
    await expect(
      streamChat({ user_id: "u1", session_id: null, message: "selam" }, t.handlers),
    ).rejects.toBeInstanceOf(DOMException);
  });

  it("API adresi tanımsızsa istek atmadan hata verir", async () => {
    vi.resetModules();
    vi.doMock("./client", async () => {
      const gercek = await vi.importActual<typeof import("./client")>("./client");
      return { ...gercek, isApiConfigured: false };
    });
    const { streamChat: kapaliStream } = await import("./chat");

    const fetchSahte = vi.fn();
    vi.stubGlobal("fetch", fetchSahte);

    // Sınıf KİMLİĞİ yerine mesaj doğrulanıyor: `vi.resetModules()` client'ı
    // ikinci kez yüklediği için ortada iki ayrı `ApiError` sınıfı oluyor ve
    // `toBeInstanceOf` yanıltıcı biçimde başarısız oluyor. Sınanmak istenen
    // şey zaten "istek atılmadan anlaşılır bir hata verildi".
    await expect(
      kapaliStream({ user_id: "u1", session_id: null, message: "selam" }, {}),
    ).rejects.toThrow("VITE_API_BASE_URL tanımlı değil");
    expect(fetchSahte).not.toHaveBeenCalled();

    vi.doUnmock("./client");
    vi.resetModules();
  });
});
