import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatGreeting, karsilamaMetni } from "./ChatGreeting";

/**
 * Karşılama, sohbetin ilk izlenimi ve tek görevi beklenti ayarlamak.
 *
 * Buradaki asıl risk görünmez olan: karşılama `messages` dizisine sahte bir
 * kayıt olarak eklenirse döküm indirme ajanın hiç üretmediği bir metni
 * deftere yazar. Bu dosya metnin kendisini ve açılış ritmini koruyor;
 * "mesaj değil" değişmezi ChatPage tarafında duruyor.
 */

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function ilerlet(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe("karsilamaMetni", () => {
  it("yalnızca İLK adı kullanır", () => {
    // `user.name` tam ad taşıyor; "Merhaba Çağan Karan." resmî bir yazışma
    // gibi duruyor, karşılamanın işi tam tersi.
    expect(karsilamaMetni("Çağan Karan")).toContain("Merhaba Çağan.");
    expect(karsilamaMetni("Çağan Karan")).not.toContain("Karan");
  });

  it("ad yoksa hitabı ADSIZ kurar, boşluk bırakmaz", () => {
    expect(karsilamaMetni(undefined)).toContain("Merhaba.");
    expect(karsilamaMetni("   ")).toContain("Merhaba.");
    expect(karsilamaMetni("")).not.toContain("Merhaba .");
  });

  it("ürün adını VİRA olarak yazar", () => {
    expect(karsilamaMetni("Çağan")).toContain("VİRA");
  });

  it("emoji İÇERMEZ", () => {
    expect(karsilamaMetni("Çağan")).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  it("kapsamı ve sınırı söyler", () => {
    // Karşılamanın değeri sıcaklık değil beklenti ayarlamak: ne yapabildiği
    // ve neyi UYDURMAYACAĞI baştan yazılı olmazsa "neden cevap vermedi"
    // anı sürpriz olur.
    const metin = karsilamaMetni("Çağan");
    expect(metin).toContain("risk");
    expect(metin).toMatch(/hisse|döviz|altın|fon/);
    expect(metin).toMatch(/tahmin yürütmem|açıkça söylerim/);
  });

  it("yatırım tavsiyesi ibaresini TAŞIMAZ", () => {
    // İbare sayfanın altında kalıcı olarak duruyor; karşılama da finansal
    // bir çıktı değil. İki yerde göstermek uyarıyı sıradanlaştırır.
    expect(karsilamaMetni("Çağan")).not.toContain("Yatırım tavsiyesi");
  });
});

describe("ChatGreeting", () => {
  it("kelime kelime açılır, tek seferde basılmaz", () => {
    render(<ChatGreeting userName="Çağan" />);

    // İlk karede henüz hiçbir şey yok: sohbetin geri kalanıyla aynı ritim.
    expect(screen.queryByText(/VİRA/)).not.toBeInTheDocument();

    ilerlet(24);
    const erken = document.body.textContent ?? "";
    expect(erken.length).toBeGreaterThan(0);
    expect(erken).not.toContain("açıkça söylerim");
  });

  it("sonunda metnin TAMAMI görünür", () => {
    // En önemli değişmez: yarım kalan bir karşılama, kullanıcının VİRA'nın
    // sınırlarını hiç okumaması demek.
    render(<ChatGreeting userName="Çağan" />);

    ilerlet(5000);

    expect(document.body.textContent).toContain("açıkça söylerim");
  });
});
