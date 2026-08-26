export type ScreenId = "dashboard" | "portfolio" | "market" | "risk" | "chat";

export interface User {
  name: string;
  initials: string;
  role: string;
}

export interface PortfolioSummary {
  totalValue: number;
  /** Elde tutulan varlıkların maliyeti. Serbest nakit HARİÇ. */
  costBasis: number;
  /**
   * Dışarıdan konan net sermaye (yatırma − çekme), serbest nakit DAHİL.
   * Kâr/zararın tabanı budur; maliyet taban alınsaydı hesapta duran para
   * kâr olarak raporlanırdı (bkz. docs/API.md).
   */
  netInvested: number;
  totalPL: number; // toplam kâr/zarar (TL)
  totalPLPct: number; // toplam kâr/zarar (%)

  // --- Yeterli geçmiş yoksa backend `null` döndürüyor; o durumda bu alanlar
  // hiç gelmez ve arayüz "—" gösterir. Sıfırla doldurmak sessizce yanlış
  // sayı üretmek olurdu (AK 5.5).
  /** Günlük değişim, TL. */
  todayChange?: number;
  /** Günlük değişim, yüzde. */
  todayChangePct?: number;
  /** Seçili dönemin zaman ağırlıklı getirisi (TWR). */
  periodReturnPct?: number;

  // --- Kaynağı olmayan alanlar. Backend karşılığı gelene kadar adapter
  // bunları DOLDURMUYOR; yalnızca tasarım verisinde bulunurlar.
  /** 0-100 kompozit risk skoru. Risk v2 bu skoru kaldırdı (7 kademe + volatilite). */
  riskScore?: number;
  /** Enflasyondan arındırılmış yıllık getiri. Sistemde enflasyon kaynağı yok. */
  realReturnPct?: number;
  dailyLoserPct?: number;
  dailyLoserNote?: string;
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
  /** Varlık sınıfının Türkçe adı. Boş bırakılırsa ekranda sonu ayraçla biten
   *  bir metin ("Tüpraş · ") görünür — bu yüzden opsiyonel değil. */
  assetClass: string;
  returnPct: number;
}

/**
 * Dashboard'daki risk kartının ihtiyacı.
 *
 * 0-100 KOMPOZİT SKOR YOK: risk metodolojisi v2 onu bilerek kaldırdı, yerine
 * volatiliteden türeyen 7 kademeli etiket geldi. Hesaplanamıyorsa alanlar
 * `null` gelir ve kart "hesaplanamadı" gösterir — 0 yazmak "riskiniz yok"
 * demek olurdu (AK 2.7 / 5.5).
 */
export interface RiskSummary {
  /** Türkçe etiket: "Çok Düşük" … "Çok Yüksek". */
  levelLabel: string | null;
  /**
   * Aynı kademenin SAYISAL karşılığı (1-7), renkli gösterge için.
   *
   * Etiketten ayrı tutuluyor: gösterge sıra bilgisine ihtiyaç duyuyor,
   * metni yeniden ayrıştırmak (etiket → sayı) çeviri değişince sessizce
   * kırılırdı.
   */
  level: number | null;
  annualizedVolatilityPct: number | null;
  /** Volatilite, kullanıcının profil bandının içinde mi? */
  withinProfile: boolean | null;
  profileLabel: string;
  /** Hesaplanamadıysa sebebi. */
  warning: string | null;
}

/**
 * Grafik dönemleri. Backend pencereleriyle birebir eşleşir
 * (`1m | 3m | 6m | 12m`); tasarımdaki "1H" (1 hafta) karşılığı olmadığı için
 * çıkarıldı — var olmayan bir pencereyi göstermek boş grafik demek olurdu.
 */
export type RangeKey = "1A" | "3A" | "6A" | "1Y";

export interface PerformancePoint {
  label: string;
  /** O günkü portföy piyasa değeri (TL). */
  portfolio: number;
  /**
   * O güne kadar dışarıdan konan kümülatif net para (TL).
   * İki çizgi arasındaki boşluk doğrudan toplam kârdır — ikinci çizgi
   * olarak endeks yerine bunun seçilme sebebi bu (bkz. docs/API.md).
   */
  invested: number;
}

export interface PerformanceRange {
  key: RangeKey;
  subtitle: string;
  points: PerformancePoint[];
  annotationIndex: number | null;
  annotationLabel?: string;
  /** Pencere portföyün ömründen uzunsa başlangıç ilk işleme kırpıldı. */
  truncatedToInception?: boolean;
  /** Dönem TWR'si — seriden türetilmez, backend'den gelir. */
  returnPct?: number | null;
}

export interface PerformanceStats {
  high: number;
  low: number;
  /** Dönemin zaman ağırlıklı getirisi (TWR) — dış para akışından arındırılmış. */
  returnPct: number | null;
  /** Dönem sonundaki değer − yatırılan (TL). */
  profit: number;
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
  /** Cevap hâlâ akıyor — balonda yanıp sönen imleç gösterilir. */
  streaming?: boolean;
  /** Hangi ajan yanıtladı (portfolio_agent, market_agent, risk_agent). FR-7 izlenebilirlik. */
  agentName?: string | null;
  /** Akış tamamlanmadan koptuysa cevap eksiktir; arayüz bunu belirtmeli. */
  incomplete?: boolean;
  /** Ajan/ağ hatası. Dolu olduğunda balon hata biçiminde gösterilir. */
  error?: string;
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
  /** Risk ucu düşerse gelmez; kart "hesaplanamadı" gösterir. */
  risk?: RiskSummary;
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
