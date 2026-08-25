import { describe, expect, it } from "vitest";
import { buildTranscript } from "./transcript";
import type { ChatMessage } from "@/types/finance";

/**
 * Döküm, sohbeti sonradan İNCELEMEK için var. O yüzden buradaki testler
 * biçimden çok şunu koruyor: bozuk bir yanıtın neden bozuk olduğu dökümde
 * görünmeli. Metnin kendisine bakarak "bu yanıt yarım mı, ajan mı patladı"
 * ayırt edilemiyor.
 */

function mesaj(over: Partial<ChatMessage> & Pick<ChatMessage, "role" | "text">): ChatMessage {
  return { id: Math.random().toString(), createdAt: "21:30", ...over };
}

describe("buildTranscript", () => {
  it("soru ve yanıtları KONUŞMA SIRASINDA yazar", () => {
    const cikti = buildTranscript(
      [
        mesaj({ role: "user", text: "İlk soru" }),
        mesaj({ role: "assistant", text: "İlk yanıt" }),
        mesaj({ role: "user", text: "İkinci soru" }),
        mesaj({ role: "assistant", text: "İkinci yanıt" }),
      ],
      "Ayşe Yılmaz",
    );

    const sira = ["İlk soru", "İlk yanıt", "İkinci soru", "İkinci yanıt"].map((p) =>
      cikti.indexOf(p),
    );
    expect(sira.every((i) => i >= 0)).toBe(true);
    expect([...sira].sort((a, b) => a - b)).toEqual(sira);
  });

  it("soruları numaralar ve kullanıcıyı başlığa yazar", () => {
    const cikti = buildTranscript(
      [
        mesaj({ role: "user", text: "Soru A" }),
        mesaj({ role: "assistant", text: "Yanıt A" }),
        mesaj({ role: "user", text: "Soru B" }),
      ],
      "Ayşe Yılmaz",
    );
    expect(cikti).toContain("[1] SORU");
    expect(cikti).toContain("[2] SORU");
    expect(cikti).toContain("Ayşe Yılmaz");
    expect(cikti).toContain("2 soru, 1 yanıt");
  });

  it("hangi ajanın cevapladığını taşır", () => {
    // İnceleme sırasında en çok işe yarayan bilgi bu: yanlış cevabın
    // yanlış ajana gitmekten mi kaynaklandığını gösteriyor.
    const cikti = buildTranscript(
      [
        mesaj({ role: "user", text: "Riskim ne?" }),
        mesaj({ role: "assistant", text: "Orta.", agentName: "risk_agent" }),
      ],
      "K",
    );
    expect(cikti).toContain("risk_agent");
  });

  it("hatayı ve yarım kalmayı AYRI AYRI işaretler", () => {
    const cikti = buildTranscript(
      [
        mesaj({ role: "user", text: "Soru" }),
        mesaj({ role: "assistant", text: "Yarım cü", error: "Zaman aşımı", incomplete: true }),
      ],
      "K",
    );
    expect(cikti).toContain("[HATA] Zaman aşımı");
    expect(cikti).toContain("[EKSİK]");
  });

  it("boş yanıtı sessizce yutmaz", () => {
    // Boş satır bırakılsaydı dökümü okuyan "yanıt gelmiş ama kopyalanmamış"
    // sanabilirdi; oysa ajan gerçekten boş dönmüş olabiliyor.
    const cikti = buildTranscript(
      [mesaj({ role: "user", text: "Soru" }), mesaj({ role: "assistant", text: "" })],
      "K",
    );
    expect(cikti).toContain("(boş yanıt)");
  });

  it("boş oturumda çökmez", () => {
    const cikti = buildTranscript([], "K");
    expect(cikti).toContain("hiç mesaj yok");
  });
});
