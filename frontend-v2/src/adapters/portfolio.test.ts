import { describe, expect, it } from "vitest";
import type { ApiHoldingRow, ApiHoldingsValuation, ApiPortfolioSummary } from "@/api/portfolio";
import { toAssetClassSummaries, toHoldings, toPortfolioPageData } from "./portfolio";

/**
 * Portfolio adapter testleri.
 *
 * Sınıf bazlı getiri holdings'ten TÜRETİLİYOR (backend sağlamıyor) — bu
 * hesaplamanın yanlış olması sessizce yanlış bir kart yüzdesi üretir,
 * tarayıcıda fark edilmez. `price_missing` satırların hem toplamlardan
 * hem de kendi satırından doğru dışlandığı/işaretlendiği ayrıca test
 * ediliyor (AK 5.5 — eksik veriyi 0/varsayımla doldurmamak).
 */

const OZET: ApiPortfolioSummary = {
  user_id: "u1",
  as_of: "2026-08-20",
  oldest_price_date: "2026-08-20",
  total_value: 2_681_069.66,
  total_cost_basis: 1_682_346.32,
  net_invested: 1_870_000,
  total_gain_loss: { amount: 811_069.66, percent: 43.37 },
  allocation: [
    { asset_class: "stock", value: 1_194_764.65, percent: 44.56 },
    { asset_class: "precious_metal", value: 452_028.34, percent: 16.86 },
    { asset_class: "cash", value: 398_326.94, percent: 14.87 },
  ],
  holdings_count: 3,
};

function holdingRow(ustuneYaz: Partial<ApiHoldingRow> = {}): ApiHoldingRow {
  return {
    symbol: "TUPRS",
    name: "Tüpraş",
    asset_class: "stock",
    currency: "TRY",
    quantity: 1428,
    current_price_try: 391.75,
    market_value_try: 559_419.0,
    weight_percent: 33.84,
    avg_cost_try: 172.63,
    cost_basis_try: 246_515.64,
    unrealized_pnl_try: 312_903.36,
    unrealized_pnl_percent: 126.91,
    realized_pnl_try: 0,
    price_missing: false,
    ...ustuneYaz,
  };
}

describe("toAssetClassSummaries", () => {
  it("holdings === null iken hiçbir sınıf için getiri hesaplamaz", () => {
    const dilimler = toAssetClassSummaries(OZET, null);
    expect(dilimler.every((d) => d.returnPct === null)).toBe(true);
    expect(dilimler).toHaveLength(3);
  });

  it("sınıf getirisini o sınıfın holdings satırlarından ağırlıklı hesaplar", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow()],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const dilimler = toAssetClassSummaries(OZET, holdings);
    const hisse = dilimler.find((d) => d.id === "stocks")!;
    // 312903.36 / 246515.64 * 100, 1 ondalığa yuvarlanmış.
    expect(hisse.returnPct).toBeCloseTo(126.9, 1);
  });

  it("price_missing satırı ağırlıklı hesaplamadan DIŞLAR", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [
        holdingRow(),
        holdingRow({
          symbol: "XYZ",
          name: "Fiyatı yok",
          price_missing: true,
          market_value_try: null,
          unrealized_pnl_try: null,
          cost_basis_try: 999_999, // dahil edilseydi sonucu bozardı
          unrealized_pnl_percent: null,
        }),
      ],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: ["XYZ"],
    };
    const dilimler = toAssetClassSummaries(OZET, holdings);
    const hisse = dilimler.find((d) => d.id === "stocks")!;
    expect(hisse.returnPct).toBeCloseTo(126.9, 1);
  });

  it("aynı sınıftaki birden fazla satırı toplayıp ağırlıklı hesaplar (canlı veriyle doğrulandı: PPF + Vadeli Mevduat)", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-07-31",
      holdings: [
        holdingRow({
          symbol: "PPF",
          asset_class: "cash",
          unrealized_pnl_try: 95_783.96,
          cost_basis_try: 283_499.98,
        }),
        holdingRow({
          symbol: "MEVDUAT-V",
          asset_class: "cash",
          unrealized_pnl_try: 0,
          cost_basis_try: 283_500.0,
        }),
      ],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const dilimler = toAssetClassSummaries(OZET, holdings);
    const nakit = dilimler.find((d) => d.id === "cash")!;
    expect(nakit.returnPct).toBeCloseTo(16.9, 1);
  });

  it("bir sınıfın hiç holdings satırı yoksa (ör. tamamı serbest nakit) 0 döner, null değil", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow()],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const dilimler = toAssetClassSummaries(OZET, holdings);
    const nakit = dilimler.find((d) => d.id === "cash")!;
    expect(nakit.returnPct).toBe(0);
  });
});

describe("toHoldings", () => {
  it("holdings === null iken boş dizi döner", () => {
    expect(toHoldings(null)).toEqual([]);
  });

  it("normal satırı Holding'e çevirir — risk ve lots kaynağı olmadığı için null/boş", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow()],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const [h] = toHoldings(holdings);
    expect(h.id).toBe("TUPRS");
    expect(h.assetClassId).toBe("stocks");
    expect(h.returnPct).toBe(126.91);
    expect(h.risk).toBeNull();
    expect(h.lots).toEqual([]);
  });

  it("price_missing satırda değer/getiri '—'/null gösterir, uydurmaz", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [
        holdingRow({
          symbol: "XYZ",
          price_missing: true,
          market_value_try: null,
          unrealized_pnl_percent: null,
          current_price_try: null,
        }),
      ],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: ["XYZ"],
    };
    const [h] = toHoldings(holdings);
    expect(h.formattedValue).toBe("—");
    expect(h.returnPct).toBeNull();
    expect(h.value).toBe(0);
  });

  it("kıymetli maden birimini gram, dövizi kendi sembolüyle gösterir", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [
        holdingRow({ symbol: "XAUTRY", asset_class: "precious_metal", quantity: 100 }),
        holdingRow({ symbol: "USDTRY", asset_class: "currency", currency: "USD", quantity: 500 }),
      ],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const [altin, dolar] = toHoldings(holdings);
    expect(altin.unitLabel).toBe("gr");
    expect(dolar.unitLabel).toBe("$");
  });
});

describe("toPortfolioPageData", () => {
  it("instrumentCount/assetClassCount özetten gelir, riskSummary kaynağı olmadığı için boş", () => {
    const data = toPortfolioPageData({ summary: OZET, holdings: null });
    expect(data.instrumentCount).toBe(3);
    expect(data.assetClassCount).toBe(3);
    expect(data.riskSummary).toEqual([]);
  });
});
