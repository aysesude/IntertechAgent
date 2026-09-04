export type ScreenId = "dashboard" | "portfolio" | "market" | "risk" | "chat" | "trade";

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
  /**
   * Kullanıcının anket puanı (1-7). `profileLabel` bundan türer.
   *
   * `level` ile KARIŞTIRMAYIN: bu kullanıcının beyan ettiği risk toleransı,
   * `level` ise portföyün ölçülen oynaklığı. İkisinin ayrışması anlamlı bir
   * bilgidir ("profil üstü").
   */
  surveyScore: number | null;
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
  /** `null`: sınıf bazlı getiri hesaplanamadı (holdings verisi yok). */
  returnPct: number | null;
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
  /** Görüntülenen Türkçe etiket, ör. "Hisse · Savunma". Filtre için DEĞİL — bkz. assetClassId. */
  assetClass: string;
  /** Filtre/eşleme için kararlı kimlik — Türkçe etiketi ayrıştırmak kırılgan olurdu. */
  assetClassId: AssetClassId;
  quantity: string;
  value: number;
  formattedValue: string;
  /** `null`: fiyatı bulunamadı (`price_missing`), getiri hesaplanamıyor. */
  returnPct: number | null;
  /**
   * 7 kademeli risk seviyesi Türkçe etiketi — Risk sayfasındaki
   * `RiskAssetRow.riskLevelLabel` ile AYNI ölçek/kaynak. `/holdings` ucunda
   * KARŞILIĞI YOK; `/api/risk/{user_id}` yanıtındaki `asset_metrics[]`den
   * sembole göre eşlenir (bkz. adapters/portfolio.ts). Eşleşme yoksa (nakit
   * kalemi, risk isteği düştü, ya da o varlığın kendi geçmişi yetersiz)
   * `null` — ekran "—" gösterir, uydurmaz (AK 5.5).
   */
  risk: string | null;
  /** `risk`'in SAYISAL karşılığı (1-7), rozet rengi için — bkz. RiskAssetRow.riskLevelOrdinal. */
  riskOrdinal: number | null;
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

export interface MarketIndicator {
  id: string;
  label: string;
  value: string;
  /** Hesaplanamadıysa `null` — 0 YAZILMAZ, "değişmedi" ile "bilinmiyor" ayrı. */
  changePct: number | null;
  /** Fiyatın ait olduğu gün ("22.08.2026"). Bugün olmak zorunda değil. */
  priceDate: string;
  /** `stale` ise fiyat beklenenden eski; arayüz bunu söylemek zorunda. */
  stale: boolean;
}

export /**
 * Haber kartı.
 *
 * `tag`, `aiSummary`, `impact`, `sourceCount` NULLABLE: canlı kaynak
 * (BloombergHT son dakika) yalnızca başlık ve zaman veriyor. Bu alanları
 * doldurmak için model çalıştırmak, başlık dışında veri olmadığı için
 * detay uydurmak demekti (CLAUDE.md "Uydurmama"). Arayüz "—" gösterir.
 */
interface NewsItem {
  id: string;
  tag: string | null;
  isPortfolioRelevant: boolean;
  source: string;
  time: string;
  title: string;
  aiSummary: string | null;
  impact: "Düşük" | "Orta" | "Yüksek" | null;
  sourceCount: number | null;
}

export interface InfluenceRow {
  id: string;
  name: string;
  /** Günlük değişim; fiyat geçmişi yoksa `null`. */
  changePct: number | null;
  /** Portföy ağırlığı; fiyatı bulunamayan varlıkta `null`. */
  weightPct: number | null;
}

export interface CalendarEvent {
  id: string;
  date: string;
  description: string;
}

/** `amount`/`formattedAmount` `null`/"—": yeterli fiyat geçmişi yoksa backend `null` döner. */
export interface ValueAtRisk {
  amount: number | null;
  formattedAmount: string;
  confidencePct: number;
  /** `value_at_risk_horizon_days`'ten üretilir (ör. "1 günlük ufukta") — sabit metin DEĞİL, ölçüm gün sayısına göre değişir. */
  horizonLabel: string;
}

/**
 * `rating`/"İyi-Kötü" gibi bir derecelendirme YOK: risksiz faiz oranı yüksek
 * olduğu için düşük volatiliteli/muhafazakâr portföylerde Sharpe sistematik
 * olarak negatif çıkar (bkz. docs/API.md — "bağlamsız gösterilmemeli").
 * `note`, bu bağlamı taşıyan kısa bir açıklama metnidir, bir yargı değil.
 */
export interface SharpeRatio {
  value: number | null;
  note: string;
}

/** Sayfanın üst şeridi: profil, ölçülen seviye ve tek cümlelik uyum yargısı. */
export interface RiskOverview {
  profileLabel: string;
  /** `null`: risk_level hesaplanamadı (yeterli fiyat geçmişi yok). */
  levelLabel: string | null;
  /**
   * `levelLabel`'ın SAYISAL karşılığı (1-7), `RiskLevelBar` için. Etiketten
   * ayrı tutuluyor: gösterge sıra bilgisine ihtiyaç duyuyor, metni yeniden
   * ayrıştırmak çeviri değişince sessizce kırılırdı (bkz. RiskSummary).
   */
  level: number | null;
  /**
   * Anket puanı (1-7) — `RiskLevelBar` bunu kullanır, `level`'i DEĞİL.
   * Dashboard'daki risk kartıyla aynı çubuğu göstermek için (bkz.
   * `RiskOverviewStrip`): ikisi farklı alan gösterirse aynı kullanıcı için
   * iki ayrı bar pozisyonu görünüyordu.
   */
  surveyScore: number | null;
  isWithinProfile: boolean | null;
  verdict: string;
}

/** Bir varlık sınıfının toplam portföy riskine katkısı. */
export interface RiskCategoryContribution {
  id: AssetClassId;
  name: string;
  weightPct: number;
  volatilityPct: number | null;
  riskContributionPct: number | null;
  color: string;
  highlightColor: string;
}

export interface RiskDiversification {
  herfindahlIndex: number;
  diversificationRatio: number | null;
  maxClassWeightPct: number;
  maxClassLabel: string | null;
}

/** Pozisyonlar tablosuyla aynı görsel dilde, varlık bazlı risk kırılımı. */
export interface RiskAssetRow {
  symbol: string;
  assetClassLabel: string;
  weightPct: number;
  volatilityPct: number | null;
  riskLevelLabel: string | null;
  /** 1-7, rozet rengi için (`RiskLevelBar`'daki LEVEL_COLORS ile aynı ölçek). */
  riskLevelOrdinal: number | null;
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
  instrumentCount: number;
  assetClassCount: number;
}

export interface MarketPageData {
  indicators: MarketIndicator[];
  news: NewsItem[];
  influence: InfluenceRow[];
  calendar: CalendarEvent[];
}

export interface RiskPageData {
  overview: RiskOverview;
  contributions: RiskCategoryContribution[];
  diversification: RiskDiversification;
  assets: RiskAssetRow[];
  valueAtRisk: ValueAtRisk;
  sharpe: SharpeRatio;
  /** Backend serbest metin döndürüyor (`warnings: string[]`) — yapılandırılmış alan yok, düz liste. */
  warnings: string[];
}

export interface ChatPageData {
  threads: ChatThread[];
  messages: ChatMessage[];
  suggestedPrompts: string[];
}
