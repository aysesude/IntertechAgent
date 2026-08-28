import type {
  AIRecommendation,
  AssetAllocationSlice,
  AssetClassId,
  AssetClassSummary,
  AssetPerformer,
  CalendarEvent,
  ChatMessage,
  ChatPageData,
  ChatThread,
  DashboardData,
  Holding,
  HoldingLot,
  InfluenceRow,
  MarketIndicator,
  MarketPageData,
  NewsItem,
  PerformanceRange,
  PerformanceStats,
  PeriodReturn,
  PortfolioPageData,
  PortfolioSummary,
  RangeKey,
  ReturnPeriodKey,
  RiskAssetRow,
  RiskCategoryContribution,
  RiskDiversification,
  RiskOverview,
  RiskPageData,
  RiskSummaryRow,
  SharpeRatio,
  Transaction,
  User,
  ValueAtRisk,
} from "@/types/finance";
import { formatTRY, formatQuantityByUnit } from "@/utils/format";
import { BRAND } from "@/utils/colors";
import { ANNUAL_INFLATION_PCT } from "@/data/insightConfig";
import { holdingTotals } from "@/utils/holdings";

export const mockUser: User = {
  name: "Elif Yılmaz",
  initials: "EY",
  role: "Bireysel Yatırımcı",
};

// costBasis'ten türeyen zincir: maliyet, toplam değerin ~%86'sı kabul
// edilip toplam K/Z ve yüzdesi buradan hesaplanıyor; hiçbiri elle sabit
// yazılmıyor. realReturnPct de bu zincirdeki nominal getiriden
// (totalPLPct) yıllık enflasyon varsayımı düşülerek bulunuyor.
const PORTFOLIO_TOTAL_VALUE = 2_847_320;
const PORTFOLIO_COST_BASIS = Math.round(PORTFOLIO_TOTAL_VALUE * 0.86);
const PORTFOLIO_TOTAL_PL = PORTFOLIO_TOTAL_VALUE - PORTFOLIO_COST_BASIS;
const PORTFOLIO_TOTAL_PL_PCT = (PORTFOLIO_TOTAL_PL / PORTFOLIO_COST_BASIS) * 100;
const PORTFOLIO_REAL_RETURN_PCT = PORTFOLIO_TOTAL_PL_PCT - ANNUAL_INFLATION_PCT;

export const mockPortfolioSummary: PortfolioSummary = {
  totalValue: PORTFOLIO_TOTAL_VALUE,
  todayChange: 18_420,
  dailyLoserPct: -2.14,
  dailyLoserNote: "Teknoloji hisseleri (3 varlık)",
  riskScore: 62,
  costBasis: PORTFOLIO_COST_BASIS,
  // Tasarım verisinde net sermaye, maliyetin biraz üzerinde (hesapta bir
  // miktar serbest nakit varmış gibi) — gerçek veride backend'den gelir.
  netInvested: Math.round(PORTFOLIO_COST_BASIS * 1.04),
  totalPL: PORTFOLIO_TOTAL_PL,
  totalPLPct: PORTFOLIO_TOTAL_PL_PCT,
  realReturnPct: PORTFOLIO_REAL_RETURN_PCT,
};

export const mockPeriodReturns: Record<ReturnPeriodKey, PeriodReturn> = {
  gunluk: { key: "gunluk", label: "Günlük", returnPct: 0.64, benchmarkPct: 0.31 },
  haftalik: { key: "haftalik", label: "Haftalık", returnPct: 1.82, benchmarkPct: 1.04 },
  aylik: { key: "aylik", label: "Aylık", returnPct: 4.26, benchmarkPct: 2.41 },
};

function subcategory(name: string, value: number, pct: number): { name: string; value: number; formattedValue: string; pct: number } {
  return { name, value, formattedValue: formatTRY(value), pct };
}

export const mockAllocation: AssetAllocationSlice[] = [
  {
    id: "stocks",
    name: "Hisse Senedi",
    value: 1_195_874,
    formattedValue: "₺1.195.874",
    pct: 42,
    color: "#1E3A8A",
    highlightColor: "#3B82F6",
    subcategories: [
      subcategory("Yerli hisse", 777_318, 65),
      subcategory("Yabancı hisse", 263_092, 22),
      subcategory("Fon", 155_464, 13),
    ],
  },
  {
    id: "precious",
    name: "Kıymetli Madenler",
    value: 626_410,
    formattedValue: "₺626.410",
    pct: 22,
    color: "#C4B5FD",
    highlightColor: "#E0D4FF",
    subcategories: [
      subcategory("Altın", 438_487, 70),
      subcategory("Gümüş", 93_962, 15),
      subcategory("Platin", 62_641, 10),
      subcategory("Paladyum", 31_320, 5),
    ],
  },
  {
    id: "fx",
    name: "Döviz",
    value: 512_518,
    formattedValue: "₺512.518",
    pct: 18,
    color: "#06B6D4",
    highlightColor: "#5EE8FA",
    subcategories: [
      subcategory("USD", 348_512, 68),
      subcategory("EUR", 128_130, 25),
      subcategory("GBP", 35_876, 7),
    ],
  },
  {
    id: "bond",
    name: "Tahvil",
    value: 341_678,
    formattedValue: "₺341.678",
    pct: 12,
    color: "#B91C1C",
    highlightColor: "#F87171",
    subcategories: [
      subcategory("Devlet", 187_923, 55),
      subcategory("Özel sektör", 85_420, 25),
      subcategory("Eurobond", 68_335, 20),
    ],
  },
  {
    id: "cash",
    name: "Nakit",
    value: 170_840,
    formattedValue: "₺170.840",
    pct: 6,
    color: "#4B5563",
    highlightColor: "#94A0AF",
    subcategories: [subcategory("Vadeli", 102_504, 60), subcategory("Vadesiz", 68_336, 40)],
  },
  // Portföyde hiç pozisyon bulunmayan bir varlık sınıfı örneği (AK-1.2):
  // listede tamamen gizlenmek yerine değeri "—"/0% olarak açıkça gösterilir.
  {
    id: "crypto",
    name: "Kripto Varlık",
    value: 0,
    formattedValue: "—",
    pct: 0,
    color: "#9CA3AF",
    highlightColor: "#D1D5DB",
    subcategories: [],
  },
];

export const mockBestPerformer: AssetPerformer = { name: "ASELS", assetClass: "Hisse · Savunma", returnPct: 12.4 };
export const mockWorstPerformer: AssetPerformer = { name: "THYAO", assetClass: "Hisse · Ulaştırma", returnPct: -4.6 };

export const mockTransactions: Transaction[] = [
  { id: "t1", title: "ASELS alım", date: "11 Ağu", detail: "120 adet @ ₺78,40", amount: 9_408, formattedAmount: "+₺9.408", direction: "in" },
  { id: "t2", title: "THYAO satım", date: "09 Ağu", detail: "60 adet @ ₺312,75", amount: -18_765, formattedAmount: "−₺18.765", direction: "out" },
  { id: "t3", title: "Gram altın alım", date: "05 Ağu", detail: "40 gr @ ₺4.180", amount: 167_200, formattedAmount: "+₺167.200", direction: "in" },
  { id: "t4", title: "Eurobond kupon ödemesi", date: "01 Ağu", detail: "yıllık %6,25", amount: 12_940, formattedAmount: "₺12.940", direction: "neutral" },
];

export const mockRecommendations: AIRecommendation[] = [
  { id: "r1", title: "Teknoloji ağırlığını 4 puan azalt", description: "Sektör yoğunlaşman %31'e ulaştı. Hedef aralığın %22–27. Kademeli satış volatiliteyi düşürür." },
  { id: "r2", title: "Nakit fazlasını kısa vadeli tahvile aktar", description: "₺170.840 nakit, enflasyon karşısında aylık ~₺4.900 reel kayıp üretiyor." },
  { id: "r3", title: "Altın pozisyonu hedefin üzerinde", description: "%22 ağırlık, dengeli profil için önerilen %15 bandının üzerinde seyrediyor." },
];

/**
 * Dönem seçici granülerlik mantığı AssetComparisonChart.tsx'teki
 * PERIOD_CONFIG ile aynı prensibi izliyor: dönem uzadıkça nokta sayısı
 * kabalaşıyor (1A günlük, 3A/6A haftalık-ikişer haftalık, 1Y aylık).
 *
 * ÖRNEK/PLACEHOLDER: değerler seed'li bir rastgele yürüyüşle üretiliyor
 * (bkz. AssetComparisonChart.tsx'teki generateSeries ile aynı yöntem).
 * Gerçek entegrasyonda bunun yerine API'den gelen tarihsel portföy/BIST
 * serisi kullanılmalı; veri şekli (PerformanceRange) aynı kalacak.
 */
const RANGE_CONFIG: Record<RangeKey, { subtitle: string; points: number; unit: "day" | "month"; stepDays?: number }> = {
  "1A": { subtitle: "Son 1 ay", points: 15, unit: "day", stepDays: 2 }, // ikişer günlük
  "3A": { subtitle: "Son 3 ay", points: 13, unit: "day", stepDays: 7 }, // haftalık
  "6A": { subtitle: "Son 6 ay", points: 13, unit: "day", stepDays: 14 }, // iki haftalık
  "1Y": { subtitle: "Son 1 yıl", points: 12, unit: "month" }, // aylık
};

const MONTH_LABELS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
// Tasarım verisinde yatırılan tutar, portföy değerinin biraz altında ve
// basamaklı ilerleyen bir çizgi olarak taklit ediliyor; gerçek veride bu
// seri backend'den (`invested_try`) olduğu gibi geliyor.
const INVESTED_CURRENT = 2_180_000;
const PORTFOLIO_STEP_VOLATILITY_PCT = 0.9;
const INVESTED_STEP_DROP_PCT = 0.45;

// Basit, deterministik (seed'li) sözde-rastgele üreteç — AssetComparisonChart.tsx'teki ile aynı.
function mulberry32(seed: number) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

function formatDayLabel(date: Date): string {
  return `${date.getDate()} ${MONTH_LABELS[date.getMonth()]}`;
}

function buildRange(key: RangeKey): PerformanceRange {
  const spec = RANGE_CONFIG[key];
  const now = new Date();

  const labels: string[] = [];
  if (spec.unit === "month") {
    for (let i = 0; i < spec.points; i++) {
      const monthsAgo = spec.points - 1 - i;
      const monthIndex = (now.getMonth() - monthsAgo + 12 * 10) % 12;
      labels.push(MONTH_LABELS[monthIndex]);
    }
  } else {
    const stepDays = spec.stepDays ?? 1;
    for (let i = 0; i < spec.points; i++) {
      const daysAgo = (spec.points - 1 - i) * stepDays;
      const d = new Date(now);
      d.setDate(d.getDate() - daysAgo);
      labels.push(formatDayLabel(d));
    }
  }

  // Geriye doğru rastgele yürüyüş: SON nokta her zaman güncel portföy/BIST
  // değerine sabitlenir, öncesi bu değerden geriye doğru üretilir — böylece
  // hangi dönem seçilirse seçilsin grafik güncel değerle biter.
  const rngPortfolio = mulberry32(seedFromString("portfolio-" + key));
  const rngInvested = mulberry32(seedFromString("invested-" + key));
  const portfolioValues = new Array<number>(spec.points);
  const investedValues = new Array<number>(spec.points);
  portfolioValues[spec.points - 1] = mockPortfolioSummary.totalValue;
  investedValues[spec.points - 1] = INVESTED_CURRENT;
  for (let i = spec.points - 2; i >= 0; i--) {
    const pNoise = (rngPortfolio() - 0.5) * 2 * PORTFOLIO_STEP_VOLATILITY_PCT;
    portfolioValues[i] = portfolioValues[i + 1] / (1 + pNoise / 100);
    // Yatırılan tutar geriye doğru yalnızca AZALIR (para yatırma anları):
    // gerçek seride de basamaklı ve monoton artan bir çizgi.
    const azalma = rngInvested() < 0.25 ? rngInvested() * INVESTED_STEP_DROP_PCT : 0;
    investedValues[i] = investedValues[i + 1] * (1 - azalma / 100);
  }

  let annotationIndex: number | null = null;
  let annotationLabel: string | undefined;
  if (key === "1Y") {
    const mayIndex = labels.indexOf("May");
    if (mayIndex !== -1) {
      annotationIndex = mayIndex;
      annotationLabel = "Mayıs düzeltmesi";
    }
  }

  return {
    key,
    subtitle: spec.subtitle,
    annotationIndex,
    annotationLabel,
    points: labels.map((label, i) => ({
      label,
      portfolio: Math.round(portfolioValues[i]),
      invested: Math.round(investedValues[i]),
    })),
  };
}

export const mockAssetClasses: AssetClassSummary[] = [
  { id: "stocks", name: "Hisse Senedi", value: 1_195_874, formattedValue: "₺1.195.874", returnPct: 6.12, weightPct: 42, icon: "stocks" },
  { id: "precious", name: "Kıymetli Madenler", value: 626_410, formattedValue: "₺626.410", returnPct: 11.4, weightPct: 22, icon: "precious" },
  { id: "fx", name: "Döviz", value: 512_518, formattedValue: "₺512.518", returnPct: -1.85, weightPct: 18, icon: "fx" },
  { id: "bond", name: "Tahvil", value: 341_678, formattedValue: "₺341.678", returnPct: 2.04, weightPct: 12, icon: "bond" },
  { id: "cash", name: "Nakit", value: 170_840, formattedValue: "₺170.840", returnPct: 0, weightPct: 6, icon: "cash" },
];

// Holding.value/formattedValue/quantity/returnPct artık lots'tan TÜRETİLİR
// (bkz. src/utils/holdings.ts) — elle ayrı yazılmıyor, tek kaynak partiler.
// Bu yüzden aşağıdaki sayılar (kâr/zarar, getiri%) önceki hardcoded
// değerlerle birebir aynı olmayabilir; partilerden hesaplanan değer geçerli
// olandır.
function makeHolding(
  id: string,
  name: string,
  assetClass: string,
  assetClassId: AssetClassId,
  risk: Holding["risk"],
  riskOrdinal: Holding["riskOrdinal"],
  currentUnitPrice: number,
  unitLabel: string,
  lotInputs: { purchaseDate: string; quantity: number; unitCost: number }[]
): Holding {
  const lots: HoldingLot[] = lotInputs.map((l, i) => ({ id: `${id}-lot${i + 1}`, ...l }));
  const totals = holdingTotals(lots, currentUnitPrice);
  return {
    id,
    name,
    assetClass,
    assetClassId,
    risk,
    riskOrdinal,
    currentUnitPrice,
    unitLabel,
    lots,
    quantity: formatQuantityByUnit(totals.totalQuantity, unitLabel),
    value: totals.totalValue,
    formattedValue: formatTRY(totals.totalValue),
    returnPct: totals.weightedReturnPct,
  };
}

export const mockHoldings: Holding[] = [
  makeHolding("h1", "ASELS", "Hisse · Savunma", "stocks", "Orta", 4, 78.4, "adet", [
    { purchaseDate: "2025-10-12", quantity: 500, unitCost: 65.5 },
    { purchaseDate: "2026-01-19", quantity: 400, unitCost: 70.0 },
    { purchaseDate: "2026-03-05", quantity: 340, unitCost: 75.0 },
  ]),
  makeHolding("h2", "GARAN", "Hisse · Bankacılık", "stocks", "Düşük", 2, 56.4, "adet", [
    { purchaseDate: "2025-09-08", quantity: 1500, unitCost: 48.0 },
    { purchaseDate: "2025-12-02", quantity: 1300, unitCost: 52.5 },
    { purchaseDate: "2026-02-14", quantity: 1000, unitCost: 55.0 },
  ]),
  makeHolding("h3", "THYAO", "Hisse · Ulaştırma", "stocks", "Yüksek", 6, 312.75, "adet", [
    { purchaseDate: "2025-08-20", quantity: 200, unitCost: 330.0 },
    { purchaseDate: "2025-11-15", quantity: 200, unitCost: 315.0 },
    { purchaseDate: "2026-01-30", quantity: 140, unitCost: 300.0 },
  ]),
  makeHolding("h4", "Gram Altın", "Emtia", "precious", "Düşük", 2, 4312, "gr", [
    { purchaseDate: "2025-07-10", quantity: 60, unitCost: 3900 },
    { purchaseDate: "2025-11-02", quantity: 45, unitCost: 4050 },
    { purchaseDate: "2026-02-20", quantity: 40, unitCost: 4180 },
  ]),
  makeHolding("h5", "USD Mevduat", "Döviz", "fx", "Orta", 4, 41.86, "$", [
    { purchaseDate: "2025-09-01", quantity: 4000, unitCost: 39.5 },
    { purchaseDate: "2025-12-10", quantity: 2400, unitCost: 40.8 },
    { purchaseDate: "2026-02-25", quantity: 2000, unitCost: 42.5 },
  ]),
  makeHolding("h6", "EUR Mevduat", "Döviz", "fx", "Orta", 4, 48.75, "€", [
    { purchaseDate: "2025-10-05", quantity: 1500, unitCost: 47.8 },
    { purchaseDate: "2026-01-08", quantity: 1200, unitCost: 48.9 },
    { purchaseDate: "2026-03-01", quantity: 600, unitCost: 49.2 },
  ]),
  makeHolding("h7", "Eurobond 2029", "Tahvil", "bond", "Düşük", 2, 1.0325, "₺", [
    { purchaseDate: "2025-06-15", quantity: 100_000, unitCost: 0.995 },
    { purchaseDate: "2025-10-20", quantity: 60_000, unitCost: 1.01 },
    { purchaseDate: "2026-01-05", quantity: 40_000, unitCost: 1.02 },
  ]),
];

// instrumentCount/assetClassCount, mockDashboard ve mockPortfolioPage arasında
// tutarlı kalsın diye ilgili dizilerin length'inden türetiliyor — hardcoded
// sayılar iki yerde birbirinden bağımsız güncellenip çakışabiliyordu.
const INSTRUMENT_COUNT = mockHoldings.length;
const ASSET_CLASS_COUNT = mockAssetClasses.length;

function formatLastUpdated(date: Date): string {
  const datePart = date.toLocaleDateString("tr-TR", { day: "numeric", month: "long" });
  const timePart = date.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  return `${datePart}, ${timePart}`;
}

export const mockPerformanceRanges: Record<RangeKey, PerformanceRange> = {
  "1A": buildRange("1A"),
  "3A": buildRange("3A"),
  "6A": buildRange("6A"),
  "1Y": buildRange("1Y"),
};

export const mockDashboard: DashboardData = {
  summary: mockPortfolioSummary,
  performance: mockPerformanceRanges,
  periodReturns: mockPeriodReturns,
  allocation: mockAllocation,
  transactions: mockTransactions,
  recommendations: mockRecommendations,
  bestPerformer: mockBestPerformer,
  worstPerformer: mockWorstPerformer,
  instrumentCount: INSTRUMENT_COUNT,
  assetClassCount: ASSET_CLASS_COUNT,
  lastUpdated: formatLastUpdated(new Date()),
};

export function computePerformanceStats(range: PerformanceRange): PerformanceStats {
  const portfolioValues = range.points.map((p) => p.portfolio);
  // Boş seri (yeni/boş portföy) — Math.max/min(...[]) ±Infinity döner;
  // high/low/profit'in nullable karşılığı yok (tip: number), 0 en doğrusu.
  // returnPct nullable OLDUĞU için burada da "hesaplanamadı" (null) dönülür,
  // 0 (uydurma "değişim yok" iddiası) değil — UI zaten null'ı "—" gösterir
  // (bkz. PerformanceChart.tsx).
  if (portfolioValues.length === 0) {
    return { high: 0, low: 0, returnPct: null, profit: 0 };
  }
  const high = Math.max(...portfolioValues);
  const low = Math.min(...portfolioValues);
  const son = range.points[range.points.length - 1];
  const ilkDeger = portfolioValues[0];
  return {
    high,
    low,
    // Gerçek veride TWR backend'den gelir; tasarım verisinde ham değişimle
    // taklit ediliyor (bu dosya yalnızca API tanımsızken devrede). İlk nokta
    // 0 ise (henüz hiç para yatırılmamış yeni hesap) bölme 0/0 = NaN
    // üretirdi ("NaN%" görünürdü) — bu durumda "hesaplanamadı" (null)
    // dönülür, uydurma bir yüzde değil (AK 5.5).
    returnPct:
      range.returnPct ?? (ilkDeger === 0 ? null : ((portfolioValues[portfolioValues.length - 1] - ilkDeger) / ilkDeger) * 100),
    profit: son.portfolio - son.invested,
  };
}

export const mockRiskSummary: RiskSummaryRow[] = [
  { id: "vol", label: "Volatilite", status: "Orta", valuePct: 14.2, color: BRAND, trend: "neutral", trendColor: "#8A8F98" },
  { id: "conc", label: "Sektör yoğunlaşması", status: "Yüksek", valuePct: 31, color: "#E63946", trend: "up", trendColor: "#E63946" },
  { id: "liq", label: "Likidite", status: "Güçlü", valuePct: 88, color: BRAND, trend: "up", trendColor: BRAND },
  { id: "fx", label: "Kur açıklığı", status: "Nötr", valuePct: 18, color: "#C7CBD4", trend: "neutral", trendColor: "#8A8F98" },
];

export const mockPortfolioPage: PortfolioPageData = {
  assetClasses: mockAssetClasses,
  holdings: mockHoldings,
  riskSummary: mockRiskSummary,
  instrumentCount: INSTRUMENT_COUNT,
  assetClassCount: ASSET_CLASS_COUNT,
};

// TASARIM VERİSİ. Yalnızca API yapılandırılmamışken gösterilir ve o durumda
// ekranda "tasarım verisi" uyarısı çıkar (bkz. MarketPage).
const MOCK_FIYAT_TARIHI = "22.08.2026";

// Şeritteki sıra ve gösterge kümesi CANLI uçla aynı tutuluyor
// (`market_service.SERIT_SIRASI`): tasarım verisi gerçek ekrandan başka
// türlü görünürse, sunucusuz çalışan demo yanıltıcı olur. 2Y tahvil buradan
// çıkarıldı — ücretsiz ve güvenilir bir kaynağı yok, dolayısıyla canlı
// şeritte hiç yer almıyor.
export const mockMarketIndicators: MarketIndicator[] = [
  { id: "XU100", label: "BIST 100", value: "11.284,00", changePct: 1.24, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "USDTRY", label: "USD/TRY", value: "₺41,86", changePct: -0.32, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "EURTRY", label: "EUR/TRY", value: "₺48,74", changePct: -0.18, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "EURUSD", label: "EUR/USD", value: "1,1644", changePct: 0.14, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "XAUTRY", label: "Gram Altın", value: "₺4.312,00", changePct: 0.87, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "XAGTRY", label: "Gram Gümüş", value: "₺48,90", changePct: 1.32, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "BRENT", label: "Brent", value: "$71,20", changePct: -1.05, priceDate: MOCK_FIYAT_TARIHI, stale: false },
  { id: "SPX", label: "S&P 500", value: "7.730,99", changePct: 0.41, priceDate: MOCK_FIYAT_TARIHI, stale: false },
];

export const mockNews: NewsItem[] = [
  {
    id: "n1",
    tag: "Portföyünü etkiler",
    isPortfolioRelevant: true,
    source: "Reuters",
    time: "32 dk önce",
    title: "TCMB faiz koridorunda daraltma sinyali verdi",
    aiSummary:
      "Üç ayrı kaynağın ortak vurgusu: politika faizinde 250 baz puanlık indirim beklentisi güçlendi. Tahvil ağırlığın nedeniyle kısa vadeli pozitif, mevduat getirinde ise kademeli gerileme anlamına geliyor.",
    impact: "Yüksek",
    sourceCount: 3,
  },
  {
    id: "n2",
    tag: "Emtia",
    isPortfolioRelevant: false,
    source: "Bloomberg HT",
    time: "1 sa önce",
    title: "Ons altın 3.480 doları test etti",
    aiSummary:
      "Merkez bankası alımları ve reel faiz beklentisi ralliyi sürdürüyor. Altın pozisyonun hedef ağırlığın 7 puan üzerinde; kâr realizasyonu için teknik seviyeler yakın.",
    impact: "Orta",
    sourceCount: 4,
  },
  {
    id: "n3",
    tag: "Bilanço",
    isPortfolioRelevant: false,
    source: "KAP",
    time: "3 sa önce",
    title: "ASELS ikinci çeyrek beklenti üstü gelir açıkladı",
    aiSummary:
      "Gelir yıllık %38 arttı, net kâr marjı 2,4 puan genişledi. Portföyündeki 1.240 lotluk pozisyon açıklama sonrası +3,4% değer kazandı.",
    impact: "Orta",
    sourceCount: 2,
  },
  {
    id: "n4",
    tag: "Makro",
    isPortfolioRelevant: false,
    source: "AA Finans",
    time: "5 sa önce",
    title: "Temmuz sanayi üretimi beklentinin altında kaldı",
    aiSummary:
      "Yıllık artış %1,8 ile %3,2 beklentisinin gerisinde. Ulaştırma ve turizm hisselerinde kısa vadeli baskı öngörülüyor; THYAO pozisyonun bu gruba dahil.",
    impact: "Düşük",
    sourceCount: 5,
  },
];

export const mockInfluence: InfluenceRow[] = [
  { id: "asels", name: "ASELS", changePct: 3.4, weightPct: 8.6 },
  { id: "garan", name: "GARAN", changePct: 1.9, weightPct: 5.2 },
  { id: "thyao", name: "THYAO", changePct: -1.6, weightPct: 4.5 },
  { id: "eurtry", name: "EUR/TRY", changePct: -0.2, weightPct: 2.6 },
];

export const mockCalendar: CalendarEvent[] = [
  { id: "c1", date: "12 Ağu", description: "TÜİK sanayi üretimi" },
  { id: "c2", date: "14 Ağu", description: "TCMB PPK toplantısı" },
  { id: "c3", date: "15 Ağu", description: "ABD TÜFE verisi" },
  { id: "c4", date: "16 Ağu", description: "ASELS 2Ç bilanço" },
];

export const mockMarketPage: MarketPageData = {
  indicators: mockMarketIndicators,
  news: mockNews,
  influence: mockInfluence,
  calendar: mockCalendar,
};

export const mockRiskOverview: RiskOverview = {
  profileLabel: "Dengeli",
  levelLabel: "Orta-Yüksek",
  level: 5,
  isWithinProfile: false,
  verdict: "Ölçülen risk seviyeniz (Orta-Yüksek), Dengeli profilinizin üzerinde.",
};

// Renkler bilinçli olarak mockAllocation'daki ile AYNI hex değerler —
// gerçek adapter (adapters/shared.ts LIGHT_ASSET_CLASS_COLORS) da bu
// paletten okuyor, mock/canlı arasında sapma olmasın diye.
export const mockRiskContributions: RiskCategoryContribution[] = [
  { id: "stocks", name: "Hisse Senedi", weightPct: 42, volatilityPct: 28.4, riskContributionPct: 54.1, color: "#1E3A8A", highlightColor: "#3B82F6" },
  { id: "precious", name: "Kıymetli Madenler", weightPct: 22, volatilityPct: 14.2, riskContributionPct: 20.9, color: "#B45309", highlightColor: "#F59E0B" },
  { id: "fx", name: "Döviz", weightPct: 18, volatilityPct: 8.9, riskContributionPct: 15.1, color: "#047857", highlightColor: "#10B981" },
  { id: "bond", name: "Borçlanma Araçları", weightPct: 12, volatilityPct: 4.4, riskContributionPct: 9.7, color: "#5B21B6", highlightColor: "#8B5CF6" },
  { id: "cash", name: "Nakit", weightPct: 6, volatilityPct: 0.3, riskContributionPct: 0.3, color: "#475569", highlightColor: "#94A3B8" },
];

export const mockRiskDiversification: RiskDiversification = {
  herfindahlIndex: 0.28,
  diversificationRatio: 1.15,
  maxClassWeightPct: 42,
  maxClassLabel: "Hisse Senedi",
};

export const mockRiskAssets: RiskAssetRow[] = [
  { symbol: "ASELS", assetClassLabel: "Hisse Senedi", weightPct: 16.4, volatilityPct: 31.2, riskLevelLabel: "Yüksek", riskLevelOrdinal: 6 },
  { symbol: "GARAN", assetClassLabel: "Hisse Senedi", weightPct: 13.9, volatilityPct: 26.8, riskLevelLabel: "Orta-Yüksek", riskLevelOrdinal: 5 },
  { symbol: "THYAO", assetClassLabel: "Hisse Senedi", weightPct: 11.7, volatilityPct: 33.5, riskLevelLabel: "Yüksek", riskLevelOrdinal: 6 },
  { symbol: "ALTIN", assetClassLabel: "Kıymetli Madenler", weightPct: 22.0, volatilityPct: 14.2, riskLevelLabel: "Düşük-Orta", riskLevelOrdinal: 3 },
  { symbol: "USD", assetClassLabel: "Döviz", weightPct: 9.6, volatilityPct: 9.4, riskLevelLabel: "Düşük", riskLevelOrdinal: 2 },
  { symbol: "EUR", assetClassLabel: "Döviz", weightPct: 8.4, volatilityPct: 8.3, riskLevelLabel: "Düşük", riskLevelOrdinal: 2 },
  { symbol: "EUROBOND", assetClassLabel: "Borçlanma Araçları", weightPct: 12.0, volatilityPct: 4.4, riskLevelLabel: "Çok Düşük", riskLevelOrdinal: 1 },
];

export const mockValueAtRisk: ValueAtRisk = {
  amount: 227_800,
  formattedAmount: "₺227.800",
  confidencePct: 95,
  horizonLabel: "1 günlük ufukta",
};

export const mockSharpeRatio: SharpeRatio = {
  value: 1.34,
  note: "Risksiz faiz oranı şu an %37,0 — bu düzey, düşük volatiliteli portföylerde Sharpe oranını sistematik olarak negatife çekebilir. Bu, portföyün kötü performans gösterdiği anlamına gelmez.",
};

export const mockRiskWarnings: string[] = [
  "CEYREK için sınırlı fiyat geçmişi nedeniyle volatilite tahmini kısıtlı.",
];

export const mockRiskPage: RiskPageData = {
  overview: mockRiskOverview,
  contributions: mockRiskContributions,
  diversification: mockRiskDiversification,
  assets: mockRiskAssets,
  valueAtRisk: mockValueAtRisk,
  sharpe: mockSharpeRatio,
  warnings: mockRiskWarnings,
};

export const mockChatThreads: ChatThread[] = [
  { id: "th1", title: "Portföy dengeleme", active: true },
  { id: "th2", title: "Altın alım zamanlaması", active: false },
  { id: "th3", title: "Emeklilik planı senaryosu", active: false },
  { id: "th4", title: "Vergi optimizasyonu", active: false },
];

export const mockChatMessages: ChatMessage[] = [
  { id: "m1", role: "assistant", text: "Merhaba Elif. Portföyünü inceledim. Bu ay getirin +4,26% ile BIST 100'ün 1,85 puan üzerinde. Nereden başlayalım?", createdAt: "10:41" },
  { id: "m2", role: "user", text: "Teknoloji ağırlığım fazla mı?", createdAt: "10:42" },
  {
    id: "m3",
    role: "assistant",
    text: "Evet. Savunma ve teknoloji hisselerin toplam portföyün %31'ini oluşturuyor; dengeli profil için önerilen üst sınır %27. Üç ay boyunca ayda %1,5 azaltım, risk skorunu 62'den 57'ye çeker ve hedef bandın merkezine yaklaştırır.",
    createdAt: "10:42",
  },
  { id: "m4", role: "user", text: "Satıştan çıkan nakiti nereye yönlendirmeliyim?", createdAt: "10:44" },
  {
    id: "m5",
    role: "assistant",
    text: "Mevcut ₺170.840 nakdinle birlikte üç dilimli kısa vadeli tahvil kademesi öneriyorum: 3 ay %36,8, 6 ay %37,4, 12 ay %38,1 bileşik. Bu yapı likiditeni korurken yıllık yaklaşık ₺48.000 ek getiri üretir.",
    createdAt: "10:44",
  },
];

export const mockChatPage: ChatPageData = {
  threads: mockChatThreads,
  messages: mockChatMessages,
  suggestedPrompts: [
    "Portföyümün dağılımı nasıl?",
    "Portföyüm ne kadar riskli?",
    "Enflasyon haberi portföyümü nasıl etkiler?",
  ],
};

export const INVESTMENT_DISCLAIMER = "Yatırım tavsiyesi değildir.";

export const mockWidgetStarterPrompts = [
  "Yatırımlarımın dağılımı nasıl?",
  "Portföyümün risk seviyesi nedir?",
  "Bu ay ne kadar kazandım/kaybettim?",
];

export function buildAssistantReply(_userText: string): ChatMessage {
  return {
    id: `m-${Date.now()}`,
    role: "assistant",
    text:
      "Portföy verilerini ve son 30 günlük piyasa akışını taradım. Bu soruyu üç başlıkta yanıtlıyorum: mevcut pozisyonun etkisi, hedef bandına uzaklık ve önerilen aksiyon adımı.",
    createdAt: new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
  };
}

export const formattedTotalValue = formatTRY(mockPortfolioSummary.totalValue);
