import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Hızlı Özet katmanının ERİŞİLEBİLİRLİK davranışı.
 *
 * Bulanık bir arka plan yalnızca görsel bir örtüdür: altındaki düğmeler
 * sekmeyle gezilebilir ve ekran okuyucuya okunabilir kalır. Buradaki üç test
 * o boşluğu kapatan üç mekanizmayı kilitliyor — odak tuzağı, `inert` ve
 * kapanışta odağın geri verilmesi.
 */

const useInsightData = vi.fn();

vi.mock("@/hooks/useInsightData", () => ({
  useInsightData: (...a: unknown[]) => useInsightData(...a),
}));

const { InsightOverlay } = await import("./InsightOverlay");

const KARTLAR = [
  { id: "genel" as const, title: "Genel Durum", body: "Genel gövde.", degraded: false },
  { id: "risk" as const, title: "Risk", body: "Risk gövdesi.", degraded: false },
];

let kok: HTMLDivElement;
let arkaPlanDugmesi: HTMLButtonElement;

beforeEach(() => {
  useInsightData.mockReturnValue({
    cards: KARTLAR,
    loading: false,
    error: null,
    refetch: vi.fn(),
  });

  // Gerçek uygulamadaki yapı: katman portal ile #root'un DIŞINA çıkıyor.
  kok = document.createElement("div");
  kok.id = "root";
  arkaPlanDugmesi = document.createElement("button");
  arkaPlanDugmesi.textContent = "Arka plan düğmesi";
  kok.appendChild(arkaPlanDugmesi);
  document.body.appendChild(kok);
});

afterEach(() => {
  kok.remove();
});

describe("InsightOverlay — erişilebilirlik", () => {
  it("açıkken arka plan INERT olur, kapanınca kalkar", () => {
    // Odak tuzağı tek başına yetmez: `inert` arka planı erişilebilirlik
    // AĞACINDAN da çıkarır, ekran okuyucu bulanık içeriği hiç okumaz.
    const { rerender } = render(
      <InsightOverlay open onClose={() => {}} activeCardId="genel" />,
      { container: document.body.appendChild(document.createElement("div")) },
    );

    expect(kok.hasAttribute("inert")).toBe(true);

    rerender(<InsightOverlay open={false} onClose={() => {}} activeCardId="genel" />);

    expect(kok.hasAttribute("inert")).toBe(false);
  });

  it("kapanışta odak, paneli AÇAN öğeye geri verilir", () => {
    // Klavye kullanıcısı panelden çıkınca listenin başına fırlamamalı.
    arkaPlanDugmesi.focus();
    expect(document.activeElement).toBe(arkaPlanDugmesi);

    const { rerender } = render(
      <InsightOverlay open onClose={() => {}} activeCardId="genel" />,
      { container: document.body.appendChild(document.createElement("div")) },
    );
    expect(document.activeElement).not.toBe(arkaPlanDugmesi);

    rerender(<InsightOverlay open={false} onClose={() => {}} activeCardId="genel" />);

    expect(document.activeElement).toBe(arkaPlanDugmesi);
  });

  it("Tab son öğeden İLK öğeye döner, arka plana kaçmaz", () => {
    render(<InsightOverlay open onClose={() => {}} activeCardId="genel" />, {
      container: document.body.appendChild(document.createElement("div")),
    });

    const dialog = screen.getByRole("dialog");
    const odaklanabilir = dialog.querySelectorAll<HTMLElement>("button");
    const ilk = odaklanabilir[0];
    const son = odaklanabilir[odaklanabilir.length - 1];

    son.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });

    expect(document.activeElement).toBe(ilk);
  });

  it("Shift+Tab ilk öğeden SON öğeye döner", () => {
    render(<InsightOverlay open onClose={() => {}} activeCardId="genel" />, {
      container: document.body.appendChild(document.createElement("div")),
    });

    const dialog = screen.getByRole("dialog");
    const odaklanabilir = dialog.querySelectorAll<HTMLElement>("button");
    const ilk = odaklanabilir[0];
    const son = odaklanabilir[odaklanabilir.length - 1];

    ilk.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(son);
  });

  it("Esc kapatır", () => {
    const kapat = vi.fn();
    render(<InsightOverlay open onClose={kapat} activeCardId="genel" />, {
      container: document.body.appendChild(document.createElement("div")),
    });

    fireEvent.keyDown(document, { key: "Escape" });

    expect(kapat).toHaveBeenCalled();
  });

  it("sorumluluk reddi katmanda görünür", () => {
    // CLAUDE.md §4: her finansal çıktı bu ibareyi taşımak zorunda.
    render(<InsightOverlay open onClose={() => {}} activeCardId="genel" />, {
      container: document.body.appendChild(document.createElement("div")),
    });

    expect(screen.getByText(/yatırım tavsiyesi değildir/i)).toBeInTheDocument();
  });
});
