export type ScreenId = "dashboard" | "portfolio" | "market" | "risk" | "chat";

export interface User {
  name: string;
  initials: string;
  role: string;
}

export interface PortfolioSummary {
  totalValue: number;
  todayChange: number;
  dailyLoserPct: number;
  dailyLoserNote: string;
  riskScore: number;
  costBasis: number; // toplam maliyet
  totalPL: number; // toplam kâr/zarar (TL)
  totalPLPct: number; // toplam kâr/zarar (%)
  realReturnPct: number; // enflasyondan arındırılmış yıllık getiri
}

export type ReturnPeriodKey = "gunluk" | "haftalik" | "aylik";

export interface PeriodReturn {
  key: ReturnPeriodKey;
  label: string;
  returnPct: number;
  benchmarkPct: number;
}

export interface AssetPerformer {
  name: string;
  assetClass: string;
  returnPct: number;
}

export type RangeKey = "1H" | "1A" | "3A" | "6A" | "1Y";

export interface PerformancePoint {
  label: string;
  portfolio: number;
  bist: number;
}

export interface PerformanceRange {
  key: RangeKey;
  subtitle: string;
  points: PerformancePoint[];
  annotationIndex: number | null;
  annotationLabel?: string;
}

export interface PerformanceStats {
  high: number;
  low: number;
  avgReturnPct: number;
  vsBenchmarkPct: number;
}

export interface AssetAllocationSubcategory {
  name: string;
  value: number;
  formattedValue: string;
  pct: number;
}

// Dashboard'daki Varlık Dağılımı donut'u ve Portfolio'daki varlık sınıfı
// kartları/ağırlık çubukları aynı varlık sınıfını referans alır — koyu
// temada iki sayfanın da aynı paletten (src/data/assetColors.ts) okuyabilmesi
// için ortak id.
export type AssetClassId = "stocks" | "precious" | "fx" | "bond" | "crypto" | "cash";

export interface AssetAllocationSlice {
  id: AssetClassId;
  name: string;
  value: number;
  formattedValue: string;
  pct: number;
  color: string;
  highlightColor: string;
  subcategories: AssetAllocationSubcategory[];
}

export interface Transaction {
  id: string;
  title: string;
  date: string;
  detail: string;
  amount: number;
  formattedAmount: string;
  direction: "in" | "out" | "neutral";
}

export interface AIRecommendation {
  id: string;
  title: string;
  description: string;
}

export interface AssetClassSummary {
  id: string;
  name: string;
  value: number;
  formattedValue: string;
  returnPct: number;
  weightPct: number;
  icon: AssetClassId;
}

// Bir enstrümanın tek bir alım partisi (lot). Holding.value/formattedValue/
// quantity/returnPct bunlardan TÜRETİLİR (bkz. src/utils/holdings.ts) — elle
// ayrı yazılmaz, tek kaynak burasıdır.
export interface HoldingLot {
  id: string;
  purchaseDate: string; // ISO tarih, ör. "2026-01-19"
  quantity: number;
  unitCost: number;
}

export interface Holding {
  id: string;
  name: string;
  assetClass: string;
  quantity: string;
  value: number;
  formattedValue: string;
  returnPct: number;
  risk: "Düşük" | "Orta" | "Yüksek";
  currentUnitPrice: number;
  unitLabel: string;
  lots: HoldingLot[];
}

export interface RiskSummaryRow {
  id: string;
  label: string;
  status: string;
  valuePct: number;
  color: string;
  trend: "up" | "neutral";
  trendColor: string;
}

export interface TargetVsActualRow {
  id: string;
  label: string;
  targetPct: number;
  actualPct: number;
  diff: number;
}

export interface MarketIndicator {
  id: string;
  label: string;
  value: string;
  changePct: number;
}

export interface NewsItem {
  id: string;
  tag: string;
  isPortfolioRelevant: boolean;
  source: string;
  time: string;
  title: string;
  aiSummary: string;
  impact: "Düşük" | "Orta" | "Yüksek";
  sourceCount: number;
}

export interface InfluenceRow {
  id: string;
  name: string;
  changePct: number;
  weightPct: number;
}

export interface CalendarEvent {
  id: string;
  date: string;
  description: string;
}

export interface ValueAtRisk {
  confidencePct: number;
  amount: number;
  formattedAmount: string;
  horizonLabel: string;
}

export interface SharpeRatio {
  value: number;
  rating: string;
  description: string;
}

export interface RiskProfile {
  score: number;
  label: string;
  targetRangeLow: number;
  targetRangeHigh: number;
  description: string;
}

export interface RiskFactor {
  id: string;
  label: string;
  value: number;
  target: number;
  note: string;
  color: string;
}

export interface StrategyRecommendation {
  id: string;
  priority: "Öncelikli" | "Orta vadeli" | "İzleme";
  title: string;
  description: string;
  expectedImpact: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: string;
}

export interface ChatThread {
  id: string;
  title: string;
  active: boolean;
}

export interface DashboardData {
  summary: PortfolioSummary;
  performance: Record<RangeKey, PerformanceRange>;
  // Backend henüz göndermeyebilir ya da hesaplama başarısız olabilir — bu
  // yüzden opsiyonel; ilgili component'ler "veri yok" fallback'i gösterir.
  periodReturns?: Partial<Record<ReturnPeriodKey, PeriodReturn>>;
  allocation: AssetAllocationSlice[];
  transactions: Transaction[];
  recommendations: AIRecommendation[];
  bestPerformer?: AssetPerformer;
  worstPerformer?: AssetPerformer;
  instrumentCount: number;
  assetClassCount: number;
  lastUpdated: string;
}

export interface PortfolioPageData {
  assetClasses: AssetClassSummary[];
  holdings: Holding[];
  riskSummary: RiskSummaryRow[];
  targetVsActual: TargetVsActualRow[];
  instrumentCount: number;
  assetClassCount: number;
}

export interface MarketPageData {
  indicators: MarketIndicator[];
  news: NewsItem[];
  influence: InfluenceRow[];
  calendar: CalendarEvent[];
}

export interface LimitedHistoryWarning {
  assetName: string;
  message: string;
}

export interface RiskPageData {
  profile: RiskProfile;
  factors: RiskFactor[];
  recommendations: StrategyRecommendation[];
  valueAtRisk: ValueAtRisk;
  sharpeRatio: SharpeRatio;
  limitedHistoryWarning?: LimitedHistoryWarning;
}

export interface ChatPageData {
  threads: ChatThread[];
  messages: ChatMessage[];
  suggestedPrompts: string[];
}
