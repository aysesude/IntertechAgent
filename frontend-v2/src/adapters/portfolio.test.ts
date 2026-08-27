import { describe, expect, it } from "vitest";
import type {
  ApiHoldingRow,
  ApiHoldingsValuation,
  ApiPortfolioSummary,
  ApiTransactionList,
  ApiTransactionRow,
} from "@/api/portfolio";
import type { ApiAssetRiskMetrics, ApiRiskAssessment } from "@/api/risk";
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

function assetRiskMetrics(ustuneYaz: Partial<ApiAssetRiskMetrics> = {}): ApiAssetRiskMetrics {
  return {
    asset_symbol: "TUPRS",
    asset_class: "stock",
    weight_percent: 33.84,
    annualized_volatility_percent: 32.46,
    risk_level: "high",
    ...ustuneYaz,
  };
}

// transaction_date canlı backend'de tam ISO datetime ("2025-08-28T11:00:00Z"),
// sadece tarih değil (curl ile doğrulandı) — testler bunu yansıtır.
function transactionRow(ustuneYaz: Partial<ApiTransactionRow> = {}): ApiTransactionRow {
  return {
    transaction_date: "2026-01-19T11:00:00Z",
    type: "buy",
    symbol: "TUPRS",
    quantity: 100,
    price: 150,
    currency: "TRY",
    fx_rate_to_try: 1,
    fee_try: 0,
    cash_amount_try: -15_000,
    position_after: 100,
    ...ustuneYaz,
  };
}

function transactionList(transactions: ApiTransactionRow[]): ApiTransactionList {
  return { user_id: "u1", start_date: null, end_date: null, transactions };
}

function riskAssessment(assetMetrics: ApiAssetRiskMetrics[]): ApiRiskAssessment {
  return {
    user_id: "u1",
    as_of: "2026-08-20",
    risk_profile: "balanced",
    risk_profile_source: "user",
    risk_survey_score: 4,
    total_value: 2_681_069.66,
    risk_level: "medium",
    is_within_profile: true,
    metrics: {
      annualized_volatility_percent: 20,
      max_drawdown_percent: 10,
      category_metrics: [],
      asset_metrics: assetMetrics,
      diversification_ratio: 1.2,
      value_at_risk_try: 10_000,
      value_at_risk_percent: 1,
      value_at_risk_confidence: 95,
      value_at_risk_horizon_days: 1,
      sharpe_ratio: 0.5,
      risk_free_rate_percent: 37,
      risk_free_rate_is_live: false,
      max_asset_weight_percent: 33.84,
      max_asset_symbol: "TUPRS",
      max_class_weight_percent: 44.56,
      max_class: "stock",
      herfindahl_index: 0.2,
      holdings_count: assetMetrics.length,
      asset_class_count: 3,
      price_points_used: 260,
    },
    warnings: [],
    disclaimer: "Bu bir yatırım tavsiyesi değildir.",
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
    expect(toHoldings(null, null)).toEqual([]);
  });

  it("normal satırı Holding'e çevirir — risk kaynağı (risk===null) verilmediyse null/boş", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow()],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const [h] = toHoldings(holdings, null);
    expect(h.id).toBe("TUPRS");
    expect(h.assetClassId).toBe("stocks");
    expect(h.returnPct).toBe(126.91);
    expect(h.risk).toBeNull();
    expect(h.riskOrdinal).toBeNull();
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
    const [h] = toHoldings(holdings, null);
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
    const [altin, dolar] = toHoldings(holdings, null);
    expect(altin.unitLabel).toBe("gr");
    expect(dolar.unitLabel).toBe("$");
  });

  // --- Risk sütunu: /holdings'te YOK, /api/risk'teki asset_metrics[]'ten
  // sembole göre eşleniyor (bkz. adapters/portfolio.ts:toHolding). ---

  it("asset_metrics'te sembole göre eşleşme varsa risk/riskOrdinal'ı doldurur", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow({ symbol: "TUPRS" })],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const risk = riskAssessment([assetRiskMetrics({ asset_symbol: "TUPRS", risk_level: "high" })]);
    const [h] = toHoldings(holdings, risk);
    expect(h.risk).toBe("Yüksek");
    expect(h.riskOrdinal).toBe(6);
  });

  it("eşleşme bulunamayan satırda (ör. nakit kalemi asset_metrics'te yok) risk null kalır", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow({ symbol: "USD-MEVDUAT", asset_class: "cash" })],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    // asset_metrics'te BAŞKA bir sembol var, USD-MEVDUAT yok.
    const risk = riskAssessment([assetRiskMetrics({ asset_symbol: "TUPRS" })]);
    const [h] = toHoldings(holdings, risk);
    expect(h.risk).toBeNull();
    expect(h.riskOrdinal).toBeNull();
  });

  it("eşleşen kaydın kendi risk_level'ı null ise (yetersiz fiyat geçmişi) yine null kalır, uydurmaz", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow({ symbol: "YENI" })],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const risk = riskAssessment([
      assetRiskMetrics({ asset_symbol: "YENI", annualized_volatility_percent: null, risk_level: null }),
    ]);
    const [h] = toHoldings(holdings, risk);
    expect(h.risk).toBeNull();
    expect(h.riskOrdinal).toBeNull();
  });

  it("risk isteği düşmüşse (risk===null) TÜM satırlarda risk null kalır, geri kalan alanlar etkilenmez", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow({ symbol: "TUPRS" })],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const [h] = toHoldings(holdings, null);
    expect(h.risk).toBeNull();
    expect(h.riskOrdinal).toBeNull();
    expect(h.value).toBe(559_419.0);
    expect(h.returnPct).toBe(126.91);
  });

  // --- Getiri Detayları paneli: ham alış geçmişi, /transactions'tan
  // sembole göre eşleniyor (bkz. adapters/portfolio.ts:lotsFromBuys).
  // Kalan-adet bazlı DEĞİL — backend'de FIFO/LIFO parti takibi yok. ---

  describe("lots (ham alış geçmişi)", () => {
    function tekHolding(): ApiHoldingsValuation {
      return {
        user_id: "u1",
        as_of: "2026-08-20",
        holdings: [holdingRow({ symbol: "TUPRS" })],
        best_performer: null,
        worst_performer: null,
        excluded_symbols: [],
      };
    }

    it("transactions === null iken lots boş kalır", () => {
      const [h] = toHoldings(tekHolding(), null, null);
      expect(h.lots).toEqual([]);
    });

    it("sembole ait 'buy' işlemlerini lots'a çevirir — TL karşılığı price * fx_rate_to_try", () => {
      const transactions = transactionList([
        transactionRow({ transaction_date: "2026-01-19T11:00:00Z", quantity: 100, price: 150, fx_rate_to_try: 1 }),
      ]);
      const [h] = toHoldings(tekHolding(), null, transactions);
      expect(h.lots).toHaveLength(1);
      expect(h.lots[0].purchaseDate).toBe("2026-01-19T11:00:00Z");
      expect(h.lots[0].quantity).toBe(100);
      expect(h.lots[0].unitCost).toBe(150);
    });

    it("döviz cinsinden işlemde birim maliyeti kur ile TL'ye çevirir", () => {
      const transactions = transactionList([
        transactionRow({ symbol: "TUPRS", price: 10, currency: "USD", fx_rate_to_try: 34.5 }),
      ]);
      const [h] = toHoldings(tekHolding(), null, transactions);
      expect(h.lots[0].unitCost).toBe(345);
    });

    it("başka sembole ait işlemler bu holding'in lots'una sızmaz", () => {
      const transactions = transactionList([transactionRow({ symbol: "GARAN" })]);
      const [h] = toHoldings(tekHolding(), null, transactions);
      expect(h.lots).toEqual([]);
    });

    it("'sell' işlemleri alış geçmişine dahil edilmez", () => {
      const transactions = transactionList([
        transactionRow({ type: "buy", transaction_date: "2026-01-19T11:00:00Z", quantity: 100 }),
        transactionRow({ type: "sell", transaction_date: "2026-03-01T11:00:00Z", quantity: 40 }),
      ]);
      const [h] = toHoldings(tekHolding(), null, transactions);
      expect(h.lots).toHaveLength(1);
      expect(h.lots[0].purchaseDate).toBe("2026-01-19T11:00:00Z");
    });

    it("price===null olan satır (birim maliyet hesaplanamaz) uydurulmadan atlanır", () => {
      const transactions = transactionList([transactionRow({ price: null })]);
      const [h] = toHoldings(tekHolding(), null, transactions);
      expect(h.lots).toEqual([]);
    });

    it("birden fazla alım en yeni tarih en üstte sıralanır", () => {
      const transactions = transactionList([
        transactionRow({ transaction_date: "2026-01-05T11:00:00Z" }),
        transactionRow({ transaction_date: "2026-06-15T11:00:00Z" }),
        transactionRow({ transaction_date: "2026-03-10T11:00:00Z" }),
      ]);
      const [h] = toHoldings(tekHolding(), null, transactions);
      expect(h.lots.map((l) => l.purchaseDate)).toEqual([
        "2026-06-15T11:00:00Z",
        "2026-03-10T11:00:00Z",
        "2026-01-05T11:00:00Z",
      ]);
    });
  });
});

describe("toPortfolioPageData", () => {
  it("instrumentCount/assetClassCount özetten gelir, riskSummary kaynağı olmadığı için boş", () => {
    const data = toPortfolioPageData({ summary: OZET, holdings: null, risk: null, transactions: null });
    expect(data.instrumentCount).toBe(3);
    expect(data.assetClassCount).toBe(3);
    expect(data.riskSummary).toEqual([]);
  });

  it("risk sağlandığında holdings'teki ilgili sembole risk sütununu taşır", () => {
    const holdings: ApiHoldingsValuation = {
      user_id: "u1",
      as_of: "2026-08-20",
      holdings: [holdingRow({ symbol: "TUPRS" })],
      best_performer: null,
      worst_performer: null,
      excluded_symbols: [],
    };
    const risk = riskAssessment([assetRiskMetrics({ asset_symbol: "TUPRS", risk_level: "low_medium" })]);
    const data = toPortfolioPageData({ summary: OZET, holdings, risk, transactions: null });
    expect(data.holdings[0].risk).toBe("Düşük-Orta");
  });
});
