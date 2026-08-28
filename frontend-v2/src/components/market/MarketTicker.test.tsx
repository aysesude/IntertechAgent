import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MarketIndicator } from "@/types/finance";
import { MarketTicker } from "./MarketTicker";

/**
 * Kayan piyasa şeridi.
 *
 * Değişmezler: kayma için liste İKİ KEZ basılır (kesintisiz döngü), az
 * göstergede kaymaz, hiç gösterge yoksa boş kart yerine sebep yazılır.
 */

function gosterge(id: string, label: string): MarketIndicator {
  return { id, label, value: "₺41,86", changePct: 0.5, priceDate: "28/08/2026", stale: false };
}

const SEKIZ = [
  gosterge("XU100", "BIST 100"),
  gosterge("USDTRY", "USD/TRY"),
  gosterge("EURTRY", "EUR/TRY"),
  gosterge("EURUSD", "EUR/USD"),
  gosterge("XAUTRY", "Gram Altın"),
  gosterge("XAGTRY", "Gram Gümüş"),
  gosterge("BRENT", "Brent"),
  gosterge("SPX", "S&P 500"),
];

describe("MarketTicker", () => {
  it("kayarken listeyi İKİ KEZ basar ve kopyayı ekran okuyucudan gizler", () => {
    // Tek kopya -%50'ye gelince boşluğa döner; kopya olmadan döngü kesilir.
    render(<MarketTicker indicators={SEKIZ} />);

    const basliklar = screen.getAllByText("BIST 100");
    expect(basliklar).toHaveLength(2);
    // Kopya erişilebilirlik ağacında yok: aynı gösterge iki kez okunmamalı.
    expect(basliklar[1].closest("[aria-hidden]")).not.toBeNull();
  });

  it("az göstergede KAYMAZ", () => {
    // Ekrandan dar bir şeridi kaydırmak, boşluğu gezdirmekten ibaret olurdu.
    render(<MarketTicker indicators={SEKIZ.slice(0, 3)} />);

    expect(screen.getAllByText("BIST 100")).toHaveLength(1);
  });

  it("gösterge yoksa boş kart değil, SEBEP gösterir", () => {
    render(<MarketTicker indicators={[]} />);

    expect(screen.getByText(/alınamadı/)).toBeInTheDocument();
  });

  it("hesaplanamayan değişimi '—' basar, sıfır göstermez", () => {
    render(<MarketTicker indicators={[{ ...gosterge("USDTRY", "USD/TRY"), changePct: null }]} />);

    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
