import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ApiInsightCard } from "@/api/insight";
import { InsightCards } from "./InsightCards";

/**
 * Akordeon kartlar.
 *
 * Üç davranış kilitli:
 *
 * 1. TIKLAMAYLA açılır, hover ile değil. Hover ile açmak fare kartlara doğru
 *    giderken içeriği değiştirir, dokunmatikte hiç çalışmaz ve kayıtlı demo
 *    videolarında kartlar kendiliğinden açılıyormuş gibi görünür.
 * 2. Gövde metni HER ZAMAN mount. Açık/kapalı durumu `aria-expanded` ve
 *    görünürlükle ifade ediliyor. Önceden gövde mount/unmount oluyordu ve
 *    kartlar "birden büyüyüp birden küçülüp sonra genişliyordu" (sahada
 *    ölçüldü, 2 Eylül 2026) — her geçişte yeniden akış tetikleniyordu.
 * 3. Başlık İKİ AYRI ELEMAN: dar hâl için dik, geniş hâl için yatay. Önce
 *    tek eleman `rotate-180` ile döndürülüyordu ve geçişte kendi ekseninde
 *    dönüyordu. Bu yüzden başlık aramaları `getAllByText` kullanır —
 *    tek eşleşme beklemek, düzeltmenin geri alındığını gizlerdi.
 */

const KARTLAR: ApiInsightCard[] = [
  { id: "genel", title: "Genel Durum", body: "Genel gövde.", degraded: false },
  { id: "portfoy", title: "Portföyünüz", body: "Portföy gövdesi.", degraded: false },
  { id: "piyasa", title: "Piyasa", body: "Piyasa gövdesi.", degraded: false },
  { id: "risk", title: "Risk", body: "Risk gövdesi.", degraded: true },
];

/** Başlığın iki kopyası da AYNI düğmenin içinde; hangisi olursa olsun. */
function kartDugmesi(baslik: string): HTMLElement {
  const dugme = screen.getAllByText(baslik)[0].closest("button");
  if (!dugme) throw new Error(`kart bulunamadı: ${baslik}`);
  return dugme;
}

/** Kartın açık olup olmadığı — akordeonun görünür sözleşmesi. */
function acikMi(baslik: string): boolean {
  return kartDugmesi(baslik).getAttribute("aria-expanded") === "true";
}

describe("InsightCards", () => {
  it("açılışta BULUNULAN SAYFANIN kartı açık gelir", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="risk" />);

    expect(acikMi("Risk")).toBe(true);
    expect(acikMi("Genel Durum")).toBe(false);
  });

  it("TIKLAMAYLA açılır ve önceki kart kapanır", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);
    expect(acikMi("Genel Durum")).toBe(true);

    fireEvent.click(kartDugmesi("Piyasa"));

    expect(acikMi("Piyasa")).toBe(true);
    expect(acikMi("Genel Durum")).toBe(false);
  });

  it("HOVER kartı AÇMAZ", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    fireEvent.mouseEnter(kartDugmesi("Piyasa"));

    expect(acikMi("Piyasa")).toBe(false);
    expect(acikMi("Genel Durum")).toBe(true);
  });

  it("gövdeler HER ZAMAN mount kalır — geçişte reflow olmasın", () => {
    // Bu, kart sıçramasının çözümü: açılıp kapanırken DOM'a hiçbir şey girip
    // çıkmıyor, yalnızca kapsayıcının genişliği ve gövdenin görünürlüğü
    // değişiyor. Gövdeyi unmount etmeye dönülürse sıçrama geri gelir.
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    for (const kart of KARTLAR) {
      expect(screen.getByText(kart.body)).toBeInTheDocument();
    }
  });

  it("kapalı kartın gövdesi erişilebilirlik ağacından ÇIKARILIR", () => {
    // Mount kalması bir yerleşim kararı; ekran okuyucunun kapalı kartın
    // metnini okuması ayrı bir sorun olurdu.
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    const kapali = screen.getByText("Piyasa gövdesi.").closest("[aria-hidden]");
    expect(kapali).not.toBeNull();
    expect(screen.getByText("Genel gövde.").closest('[aria-hidden="true"]')).toBeNull();
  });

  it("degraded kart SEBEBİNİ söyler", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="risk" />);

    expect(screen.getByText(/özetlenemedi/)).toBeInTheDocument();
  });

  it("dört kartın başlığı da her zaman görünür", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    for (const kart of KARTLAR) {
      expect(screen.getAllByText(kart.title).length).toBeGreaterThan(0);
    }
  });

  it("başlık DÖNDÜRÜLMÜYOR — dik ve yatay iki ayrı eleman", () => {
    // Tek elemanı `rotate` ile çevirmeye dönülürse başlık, kart geçişlerinde
    // kendi ekseninde döner (sahada ölçüldü, 2 Eylül 2026).
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    const kopyalar = screen.getAllByText("Piyasa");
    expect(kopyalar.length).toBe(2);

    for (const eleman of kopyalar) {
      expect(eleman.className).not.toMatch(/rotate/);
    }
  });
});
