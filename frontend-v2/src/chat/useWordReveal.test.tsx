import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWordReveal } from "./useWordReveal";

/**
 * Kancanın tek işi: gelen metne ekranın SABİT TEMPODA yetişmesi.
 *
 * Buradaki asıl risk gözle görülmez: metnin bir kısmı hiç açılmadan kalırsa
 * kullanıcı EKSİK bir finansal cevap okur ve eksik olduğunu anlamaz. O
 * yüzden testlerin çoğu "sonunda metnin tamamı görünür" değişmezini
 * koruyor.
 */

function Panel({ metin, aktif }: { metin: string; aktif: boolean }) {
  const gorunen = useWordReveal(metin, aktif);
  return <span data-testid="gorunen">{gorunen}</span>;
}

function gorunen(): string {
  return screen.getByTestId("gorunen").textContent ?? "";
}

/** Sahte zamanı ilerletir; interval'ın tetiklediği state React'e işlenir. */
function turlariIlerlet(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  // jsdom'da matchMedia yok; "hareketi azalt" KAPALI kabul ediliyor ki
  // animasyon yolu sınansın.
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

describe("useWordReveal", () => {
  it("metni tek seferde değil, KADEMELİ açar", () => {
    // Gerçek akış BOŞ metinle mount olur (ChatBubble, token gelmeden önce
    // yanıt balonunu çiziyor) ve metin sonra büyür.
    const uzun = Array.from({ length: 40 }, (_, i) => `kelime${i}`).join(" ");
    const { rerender } = render(<Panel metin="" aktif />);
    expect(gorunen()).toBe("");

    rerender(<Panel metin={uzun} aktif />);
    turlariIlerlet(50);

    const ilk = gorunen();
    expect(ilk.length).toBeGreaterThan(0);
    expect(ilk.length).toBeLessThan(uzun.length);
  });

  it("TAMAMLANMIŞ bir mesaj yeniden çizilince baştan yazılmaz", () => {
    // Sohbet geçmişindeki her mesaj, listeye yeni bir mesaj eklendiğinde
    // yeniden render oluyor. Kanca her mount'ta sıfırdan başlasaydı eski
    // yanıtların tamamı aynı anda yeniden yazılırdı.
    const metin = Array.from({ length: 40 }, (_, i) => `kelime${i}`).join(" ");
    render(<Panel metin={metin} aktif={false} />);
    expect(gorunen()).toBe(metin);
  });

  it("KELİME sınırında keser — yarım kelime göstermez", () => {
    // Harf harf açılsaydı "1.569.4" gibi yarım bir tutar görünürdü; finansal
    // bir metinde bu, bir an için YANLIŞ sayı göstermek demek.
    const tam = "portföyünüzün toplam değeri 1.569.468 TL";
    const { rerender } = render(<Panel metin="" aktif />);
    rerender(<Panel metin={tam} aktif />);
    turlariIlerlet(50);

    const parca = gorunen();
    // Açılan metin, tam metnin kelime sınırındaki bir ön eki olmalı.
    expect(tam.startsWith(parca)).toBe(true);
    if (parca.length > 0) {
      const sonrasi = tam[parca.length];
      expect(sonrasi === undefined || sonrasi === " ").toBe(true);
    }
  });

  it("akış bitince metnin TAMAMI görünür", () => {
    // En önemli değişmez: eksik kalan bir finansal cevap, eksik olduğu
    // belli olmadan okunur.
    const metin = Array.from({ length: 120 }, (_, i) => `k${i}`).join(" ");
    const { rerender } = render(<Panel metin="" aktif />);
    rerender(<Panel metin={metin} aktif />);
    turlariIlerlet(100);
    rerender(<Panel metin={metin} aktif={false} />);
    turlariIlerlet(3000);

    expect(gorunen()).toBe(metin);
  });

  it("metin uzadıkça yetişmeye devam eder", () => {
    const { rerender } = render(<Panel metin="" aktif />);
    rerender(<Panel metin="bir iki" aktif />);
    turlariIlerlet(500);
    expect(gorunen()).toBe("bir iki");

    rerender(<Panel metin="bir iki üç dört" aktif />);
    turlariIlerlet(500);
    expect(gorunen()).toBe("bir iki üç dört");
  });

  it("YENİ bir mesaj başlayınca baştan açar", () => {
    // Metin uzamak yerine değişirse (yeni yanıt) sayaç sıfırlanmazsa yeni
    // metnin ortasından başlanır ve baş tarafı hiç görünmez.
    const { rerender } = render(<Panel metin="eski yanıt tamamlandı" aktif={false} />);
    turlariIlerlet(500);
    expect(gorunen()).toBe("eski yanıt tamamlandı");

    rerender(<Panel metin="yeni" aktif />);
    expect(gorunen()).toBe("");
    turlariIlerlet(500);
    expect(gorunen()).toBe("yeni");
  });

  it("hareket azaltma tercihinde ANINDA gösterir", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: true,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const metin = Array.from({ length: 60 }, (_, i) => `k${i}`).join(" ");
    const { rerender } = render(<Panel metin="" aktif />);
    rerender(<Panel metin={metin} aktif />);
    expect(gorunen()).toBe(metin);
  });
});
