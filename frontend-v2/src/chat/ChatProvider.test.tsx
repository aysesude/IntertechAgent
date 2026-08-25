import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatStreamHandlers } from "@/api/chat";

/**
 * ChatProvider testleri.
 *
 * Buradaki incelikler tarayıcıda kolay gözden kaçıyor: ajan hata verdiğinde
 * hiç token gelmemesi, akışın yarıda kopması, iki mount noktasının aynı
 * oturumu paylaşması. Hepsi ancak belirli bir olay dizisinde ortaya çıkıyor,
 * elle denerken ise genelde mutlu yol yaşanıyor.
 */

const streamChat = vi.fn();

vi.mock("@/api/chat", () => ({
  streamChat: (...args: unknown[]) => streamChat(...args),
}));

vi.mock("@/auth/AuthContext", () => ({
  useCurrentUserId: () => "kullanici-1",
}));

const { ChatProvider, useChat } = await import("./ChatProvider");

/** Sohbeti kullanan iki ayrı mount noktasını taklit eder (sayfa + widget). */
function Panel({ etiket }: { etiket: string }) {
  const { messages, sending, sendMessage, resetSession } = useChat();
  return (
    <div>
      <span data-testid={`${etiket}-sayi`}>{messages.length}</span>
      <span data-testid={`${etiket}-sending`}>{String(sending)}</span>
      <ol>
        {messages.map((m) => (
          <li key={m.id} data-testid={`${etiket}-mesaj`}>
            {m.role}|{m.text}|{m.streaming ? "akiyor" : "durdu"}|{m.error ?? "-"}|
            {m.incomplete ? "eksik" : "tam"}|{m.agentName ?? "-"}
          </li>
        ))}
      </ol>
      <button onClick={() => void sendMessage("Portföyüm nasıl?")}>{etiket}-gonder</button>
      <button onClick={resetSession}>{etiket}-sifirla</button>
    </div>
  );
}

function renderProvider() {
  return render(
    <ChatProvider>
      <Panel etiket="sayfa" />
      <Panel etiket="widget" />
    </ChatProvider>,
  );
}

function mesajlar(etiket: string): string[] {
  return screen.queryAllByTestId(`${etiket}-mesaj`).map((el) => el.textContent ?? "");
}

/** `streamChat`i, verilen olayları sırayla yayan bir sahteyle değiştirir. */
function akisTanimla(senaryo: (h: ChatStreamHandlers) => void | Promise<void>) {
  streamChat.mockImplementation(async (_istek: unknown, handlers: ChatStreamHandlers) => {
    await senaryo(handlers);
  });
}

beforeEach(() => {
  streamChat.mockReset();
});

describe("mutlu yol", () => {
  it("token'ları biriktirip cevabı oluşturur", async () => {
    akisTanimla((h) => {
      h.onSession?.({ session_id: "s1" });
      h.onToken?.({ delta: "Portföyünüz " });
      h.onToken?.({ delta: "iyi durumda." });
      h.onDone?.({
        agent: "portfolio_agent",
        final_answer: "Portföyünüz iyi durumda.",
        data: null,
      });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });

    await waitFor(() => expect(screen.getByTestId("sayfa-sending")).toHaveTextContent("false"));
    expect(mesajlar("sayfa")).toEqual([
      "user|Portföyüm nasıl?|durdu|-|tam|-",
      "assistant|Portföyünüz iyi durumda.|durdu|-|tam|portfolio_agent",
    ]);
  });

  it("ikinci mesajda oturum kimliğini geri gönderir", async () => {
    // Gönderilmezse her mesaj yeni bir oturum açar ve ajan önceki
    // konuşmayı bağlam olarak göremez.
    akisTanimla((h) => {
      h.onSession?.({ session_id: "s1" });
      h.onDone?.({ agent: null, final_answer: "ok", data: null });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });
    await waitFor(() => expect(screen.getByTestId("sayfa-sending")).toHaveTextContent("false"));

    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });
    await waitFor(() => expect(screen.getByTestId("sayfa-sending")).toHaveTextContent("false"));

    expect(streamChat.mock.calls[0][0]).toMatchObject({ session_id: null });
    expect(streamChat.mock.calls[1][0]).toMatchObject({ session_id: "s1" });
  });
});

describe("ajan cevap üretemediğinde", () => {
  it("hiç token gelmezse final_answer'ı kullanır", async () => {
    // GERİLEME TESTİ. Ajan başarısız olduğunda (ör. RAG sonuç bulamadı)
    // `on_token` hiç çağrılmıyor; cevap YALNIZCA `done` içindeki
    // `final_answer`'da geliyor. Bu düşünülmezse balon boş kalır ve
    // kullanıcı hiçbir şey olmamış sanır.
    akisTanimla((h) => {
      h.onSession?.({ session_id: "s1" });
      h.onDone?.({
        agent: "market_agent",
        final_answer: "Bu konuda doğrulanmış bilgi bulunamadı.",
        data: null,
      });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });

    await waitFor(() =>
      expect(mesajlar("sayfa")[1]).toContain("Bu konuda doğrulanmış bilgi bulunamadı."),
    );
  });

  it("token'lar aktıysa final_answer metnin üzerine YAZMAZ", async () => {
    akisTanimla((h) => {
      h.onToken?.({ delta: "akan metin" });
      h.onDone?.({ agent: null, final_answer: "BASKA BIR SEY", data: null });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });

    await waitFor(() => expect(mesajlar("sayfa")[1]).toContain("akan metin"));
    expect(mesajlar("sayfa")[1]).not.toContain("BASKA BIR SEY");
  });

  it("error olayını balonda gösterir", async () => {
    akisTanimla((h) => {
      h.onError?.({ message: "Ajan yanıt veremedi." });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });

    await waitFor(() => expect(mesajlar("sayfa")[1]).toContain("Ajan yanıt veremedi."));
    expect(mesajlar("sayfa")[1]).toContain("durdu");
  });

  it("ağ hatasında balonu hataya çevirir, sonsuza dek akıyor bırakmaz", async () => {
    streamChat.mockRejectedValue(new Error("Sunucuya ulaşılamadı."));

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });

    await waitFor(() => expect(mesajlar("sayfa")[1]).toContain("Sunucuya ulaşılamadı."));
    expect(mesajlar("sayfa")[1]).toContain("durdu");
    expect(screen.getByTestId("sayfa-sending")).toHaveTextContent("false");
  });

  it("akış done gelmeden biterse cevabı EKSİK olarak işaretler", async () => {
    // Yarım kalan cevabın tam sanılmaması gerekiyor; sunucu da bu durumu
    // `status: incomplete` ile kaydediyor.
    akisTanimla((h) => {
      h.onToken?.({ delta: "yarım kalan" });
      // done YOK — akış sessizce bitiyor
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });

    await waitFor(() => expect(mesajlar("sayfa")[1]).toContain("eksik"));
    expect(mesajlar("sayfa")[1]).toContain("yarım kalan");
  });
});

describe("paylaşılan oturum", () => {
  it("widget'ta gönderilen mesaj sayfada da görünür", async () => {
    // İkisi ayrı state tutsaydı widget'ta başlayan konuşma sayfaya
    // geçildiğinde kaybolurdu.
    akisTanimla((h) => {
      h.onToken?.({ delta: "ortak cevap" });
      h.onDone?.({ agent: null, final_answer: "ortak cevap", data: null });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("widget-gonder").click();
    });

    await waitFor(() => expect(screen.getByTestId("sayfa-sayi")).toHaveTextContent("2"));
    expect(mesajlar("sayfa")[1]).toContain("ortak cevap");
    expect(mesajlar("widget")[1]).toContain("ortak cevap");
  });

  it("yeni sohbet mesajları ve oturum kimliğini sıfırlar", async () => {
    akisTanimla((h) => {
      h.onSession?.({ session_id: "s1" });
      h.onDone?.({ agent: null, final_answer: "ok", data: null });
    });

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });
    await waitFor(() => expect(screen.getByTestId("sayfa-sayi")).toHaveTextContent("2"));

    await act(async () => {
      screen.getByText("sayfa-sifirla").click();
    });
    expect(screen.getByTestId("sayfa-sayi")).toHaveTextContent("0");

    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });
    await waitFor(() => expect(screen.getByTestId("sayfa-sending")).toHaveTextContent("false"));
    // Sıfırlamadan sonra eski oturuma devam edilmemeli.
    expect(streamChat.mock.calls[1][0]).toMatchObject({ session_id: null });
  });

  it("cevap beklenirken ikinci mesaj gönderilmez", async () => {
    // Aksi halde iki akış aynı balonu yazmaya çalışır ve metin karışır.
    let cozumle: (() => void) | undefined;
    streamChat.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          cozumle = resolve;
        }),
    );

    renderProvider();
    await act(async () => {
      screen.getByText("sayfa-gonder").click();
    });
    expect(screen.getByTestId("sayfa-sending")).toHaveTextContent("true");

    await act(async () => {
      screen.getByText("widget-gonder").click();
    });
    expect(streamChat).toHaveBeenCalledTimes(1);

    await act(async () => {
      cozumle?.();
    });
  });
});
