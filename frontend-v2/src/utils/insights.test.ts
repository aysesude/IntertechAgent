import { describe, expect, it } from "vitest";
import { buildInsights } from "@/utils/insights";
import {
  BENCHMARK_GAP_PCT,
  CASH_LIMIT_PCT,
  FX_LIMIT_PCT,
  MAX_INSIGHTS,
  MONTHLY_INFLATION_PCT,
  RISK_BAND,
  SINGLE_HOLDING_LIMIT_PCT,
  STRONG_RETURN_PCT,
  WEAK_RETURN_PCT,
  WEIGHT_DEVIATION_LIMIT,
} from "@/data/insightConfig";
import type {
  AssetAllocationSlice,
  DashboardData,
  Holding,
  PerformanceRange,
  PortfolioPageData,
  PortfolioSummary,
  RangeKey,
  TargetVsActualRow,
} from "@/types/finance";

function emptyRange(key: RangeKey): PerformanceRange {
  return { key, subtitle: "", points: [], annotationIndex: null };
}

// PortfolioSummary bu test yazildiktan sonra iki kez degisti; sabitler tek
// yerde toplandi ki tip bir daha genislediginde tek satir degissin.
function baseSummary(overrides: Partial<PortfolioSummary> = {}): PortfolioSummary {
  return {
    totalValue: 1_000_000,
    todayChange: 0,
    netInvested: 900_000,
    riskScore: 50,
    costBasis: 900_000,
    totalPL: 100_000,
    totalPLPct: 11.1,
    realReturnPct: 0,
    ...overrides,
  };
}

function baseDashboard(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    summary: baseSummary(),
    performance: {
      "1A": emptyRange("1A"),
      "3A": emptyRange("3A"),
      "6A": emptyRange("6A"),
      "1Y": emptyRange("1Y"),
    },
    allocation: [],
    transactions: [],
    recommendations: [],
    instrumentCount: 0,
    assetClassCount: 0,
    lastUpdated: "test",
    ...overrides,
  };
}

function basePortfolio(overrides: Partial<PortfolioPageData> = {}): PortfolioPageData {
  return {
    assetClasses: [],
    holdings: [],
    riskSummary: [],
    targetVsActual: [],
    instrumentCount: 0,
    assetClassCount: 0,
    ...overrides,
  };
}

function makeHolding(overrides: Partial<Holding> & Pick<Holding, "id" | "name" | "value" | "returnPct">): Holding {
  return {
    assetClass: "Test",
    quantity: "1",
    formattedValue: "",
    risk: "Orta",
    // Lot bazli alanlar da sonradan eklendi; testler bunlari kullanmiyor
    // ama tip zorunlu tutuyor.
    currentUnitPrice: 0,
    unitLabel: "adet",
    lots: [],
    ...overrides,
  };
}

function makeAllocationSlice(overrides: Partial<AssetAllocationSlice> & Pick<AssetAllocationSlice, "name" | "value" | "pct">): AssetAllocationSlice {
  return {
    // Varlik sinifi kimligi sonradan zorunlu oldu (koyu tema paleti icin).
    id: "stocks",
    formattedValue: "",
    color: "#000",
    highlightColor: "#000",
    subcategories: [],
    ...overrides,
  };
}

describe("buildInsights", () => {
  it("K1 AGIRLIK_SAPMASI: hedeften sınırın üzerinde sapan satır için içgörü üretir", () => {
    const row: TargetVsActualRow = {
      id: "stocks",
      label: "Hisse",
      targetPct: 30,
      actualPct: 30 + WEIGHT_DEVIATION_LIMIT + 2,
      diff: WEIGHT_DEVIATION_LIMIT + 2,
    };
    const dashboard = baseDashboard();
    const portfolio = basePortfolio({ targetVsActual: [row] });

    const result = buildInsights(dashboard, portfolio);

    expect(result.some((i) => i.id === `k1-agirlik-sapmasi-${row.id}`)).toBe(true);
  });

  it("K2 NAKIT_FAZLASI: nakit ağırlığı sınırın üzerindeyse aylık reel kayıp bildirir", () => {
    const cashValue = 200_000;
    const dashboard = baseDashboard({
      allocation: [makeAllocationSlice({ name: "Nakit", value: cashValue, pct: CASH_LIMIT_PCT + 3 })],
    });

    const result = buildInsights(dashboard, basePortfolio());
    const insight = result.find((i) => i.id === "k2-nakit-fazlasi");

    expect(insight).toBeDefined();
    expect(insight?.amountTRY).toBeCloseTo(-(cashValue * MONTHLY_INFLATION_PCT) / 100);
  });

  it("K3 TEK_VARLIK_YOGUNLASMASI: tek varlığın payı sınırı aşıyorsa uyarır", () => {
    const totalValue = 1_000_000;
    const holding = makeHolding({ id: "h1", name: "ASELS", value: (totalValue * (SINGLE_HOLDING_LIMIT_PCT + 5)) / 100, returnPct: 1 });
    const dashboard = baseDashboard({ summary: baseSummary({ totalValue }) });
    const portfolio = basePortfolio({ holdings: [holding] });

    const result = buildInsights(dashboard, portfolio);

    expect(result.some((i) => i.id === `k3-tek-varlik-yogunlasmasi-${holding.id}`)).toBe(true);
  });

  it("K4 RISK_SKORU_BANDI: risk skoru bandın dışındaysa hangi yönde olduğunu bildirir", () => {
    const dashboard = baseDashboard({
      summary: baseSummary({ riskScore: RISK_BAND.high + 10 }),
    });

    const result = buildInsights(dashboard, basePortfolio());
    const insight = result.find((i) => i.id === "k4-risk-skoru-bandi");

    expect(insight).toBeDefined();
    expect(insight?.title).toContain("üzerinde");
  });

  it("K5 ZAYIF_PERFORMANS: eşik altındaki en kötü pozisyonu bildirir", () => {
    const worse = makeHolding({ id: "h1", name: "Kötü", value: 100_000, returnPct: WEAK_RETURN_PCT - 5 });
    const lessWorse = makeHolding({ id: "h2", name: "Az Kötü", value: 100_000, returnPct: WEAK_RETURN_PCT - 1 });
    const portfolio = basePortfolio({ holdings: [lessWorse, worse] });

    const result = buildInsights(baseDashboard(), portfolio);
    const insight = result.find((i) => i.id.startsWith("k5-"));

    expect(insight?.id).toBe(`k5-zayif-performans-${worse.id}`);
  });

  it("K6 GUCLU_PERFORMANS: eşik üstündeki en iyi pozisyonu bildirir", () => {
    const best = makeHolding({ id: "h1", name: "İyi", value: 100_000, returnPct: STRONG_RETURN_PCT + 5 });
    const good = makeHolding({ id: "h2", name: "Daha Az İyi", value: 100_000, returnPct: STRONG_RETURN_PCT + 1 });
    const portfolio = basePortfolio({ holdings: [good, best] });

    const result = buildInsights(baseDashboard(), portfolio);
    const insight = result.find((i) => i.id.startsWith("k6-"));

    expect(insight?.id).toBe(`k6-guclu-performans-${best.id}`);
    expect(insight?.severity).toBe("olumlu");
  });

  it("K7 BENCHMARK_FARKI: fark eşiği aşarsa yöne göre olumlu/uyari üretir", () => {
    const dashboard = baseDashboard({
      periodReturns: {
        aylik: { key: "aylik", label: "Ay", returnPct: 5, benchmarkPct: 5 - (BENCHMARK_GAP_PCT + 1) },
      },
    });

    const result = buildInsights(dashboard, basePortfolio());
    const insight = result.find((i) => i.id === "k7-benchmark-farki");

    expect(insight?.severity).toBe("olumlu");
  });

  it("K8 DOVIZ_ACIKLIGI: döviz ağırlığı sınırın üzerindeyse bilgilendirir", () => {
    const dashboard = baseDashboard({
      allocation: [makeAllocationSlice({ name: "Döviz", value: 300_000, pct: FX_LIMIT_PCT + 4 })],
    });

    const result = buildInsights(dashboard, basePortfolio());
    const insight = result.find((i) => i.id === "k8-doviz-acikligi");

    expect(insight?.severity).toBe("bilgi");
  });

  it("sonucu severity sonra |amountTRY| ile sıralar ve MAX_INSIGHTS ile sınırlar", () => {
    const totalValue = 1_000_000;
    const rows: TargetVsActualRow[] = [
      { id: "a", label: "A", targetPct: 10, actualPct: 10 + WEIGHT_DEVIATION_LIMIT + 1, diff: WEIGHT_DEVIATION_LIMIT + 1 },
      { id: "b", label: "B", targetPct: 10, actualPct: 10 + WEIGHT_DEVIATION_LIMIT + 10, diff: WEIGHT_DEVIATION_LIMIT + 10 },
    ];
    const dashboard = baseDashboard({
      summary: baseSummary({ totalValue, riskScore: RISK_BAND.high + 10 }),
      allocation: [
        makeAllocationSlice({ name: "Nakit", value: 200_000, pct: CASH_LIMIT_PCT + 3 }),
        makeAllocationSlice({ name: "Döviz", value: 300_000, pct: FX_LIMIT_PCT + 4 }),
      ],
    });
    const portfolio = basePortfolio({ targetVsActual: rows });

    const result = buildInsights(dashboard, portfolio);

    expect(result.length).toBeLessThanOrEqual(MAX_INSIGHTS);
    // K8 (bilgi) tetiklenmiş olsa bile uyari/olumlu öğeler daha fazla
    // olduğundan MAX_INSIGHTS=3 ile kesilip listeye girmemeli.
    expect(result.every((i) => i.severity !== "bilgi")).toBe(true);
    // "B" satırının sapması "A"dan büyük — önce gelmeli.
    expect(result[0].id).toBe("k1-agirlik-sapmasi-b");
  });
});
