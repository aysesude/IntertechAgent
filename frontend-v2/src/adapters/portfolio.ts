import type {
  ApiAssetClass,
  ApiHoldingRow,
  ApiHoldingsValuation,
  ApiPortfolioSummary,
  ApiTransactionList,
  ApiTransactionRow,
} from "@/api/portfolio";
import type { ApiAssetRiskMetrics, ApiRiskAssessment } from "@/api/risk";
import { ASSET_CLASS_IDS, ASSET_CLASS_LABELS, RISK_LEVEL_LABELS, RISK_LEVEL_ORDINALS } from "@/adapters/shared";
import { formatQuantityByUnit, formatTRY } from "@/utils/format";
import type { AssetClassSummary, Holding, HoldingLot, PortfolioPageData } from "@/types/finance";

/**
 * Backend'in portföy/holdings çıktısını Portfolio sayfasının görünüm
 * modeline çevirir. `adapters/dashboard.ts` ile aynı ilke: SAF fonksiyonlar,
 * kaynağı olmayan alan uydurulmaz (AK 5.5/5.10).
 */

// ---------------------------------------------------------------------------
// Enstrüman birimi
// ---------------------------------------------------------------------------

/**
 * Backend miktarın hangi birimde olduğunu SÖYLEMİYOR (`ApiHoldingRow`'da
 * "unit" alanı yok) — varlık sınıfından çıkarılıyor. Kıymetli maden gram
 * cinsinden (uygulama genelinde "Gram Altın" kuralı, bkz. docs/API.md
 * `XAUTRY`), hisse/borçlanma aracı adet. Döviz için enstrümanın kendi para
 * birimi sembolü kullanılıyor.
 */
function unitLabelFor(assetClass: ApiAssetClass, currency: string): string {
  if (assetClass === "precious_metal") return "gr";
  if (assetClass === "currency") {
    if (currency === "USD") return "$";
    if (currency === "EUR") return "€";
    return currency;
  }
  return "adet";
}

// ---------------------------------------------------------------------------
// Varlık sınıfı kartları
// ---------------------------------------------------------------------------

/**
 * Bir varlık sınıfının ağırlıklı gerçekleşmemiş K/Z yüzdesi.
 *
 * Backend `/portfolio` özetinde sınıf başına getiri YOK, yalnızca değer/pay.
 * Bu yüzden `/holdings` satırlarından türetiliyor — gerçek veriden
 * hesaplanan bir toplulaştırma, uydurma değil.
 *
 * `holdings === null`: `/holdings` ucu düşmüş, hiçbir sınıf için hesaplanamaz.
 *
 * `cash` sınıfı GENELDE satır İÇERİR (canlı veriyle doğrulandı): para
 * piyasası fonu/vadeli mevduat gibi getirili nakit araçları `asset_class:
 * "cash"` satırı olarak gelir, maliyet/K-Z de onlarınkinden hesaplanır.
 * Yalnızca SERBEST (hiçbir araca bağlanmamış) nakit holdings'te satır
 * açmaz — o kısım `/portfolio` özetindeki `cash` payını büyütür ama
 * paydaya (`cost_basis_try`) girmez, ki bu doğrudur: serbest nakdin
 * nominal TL değeri değişmez. Kullanıcının TÜM nakdi serbestse (hiç
 * getirili nakit aracı yoksa) döngü hiç satır bulamaz ve `costBasis === 0`
 * dalına düşülür — 0 döner, "hesaplanamadı" değil.
 */
function weightedClassReturnPct(
  assetClass: ApiAssetClass,
  holdings: ApiHoldingsValuation | null,
): number | null {
  if (holdings === null) return null;

  let pnl = 0;
  let costBasis = 0;
  for (const h of holdings.holdings) {
    if (h.asset_class !== assetClass || h.price_missing) continue;
    pnl += h.unrealized_pnl_try ?? 0;
    costBasis += h.cost_basis_try;
  }
  if (costBasis === 0) return 0;
  return Math.round((pnl / costBasis) * 1000) / 10;
}

export function toAssetClassSummaries(
  ozet: ApiPortfolioSummary,
  holdings: ApiHoldingsValuation | null,
): AssetClassSummary[] {
  return ozet.allocation.map((dilim) => {
    const id = ASSET_CLASS_IDS[dilim.asset_class];
    return {
      id,
      name: ASSET_CLASS_LABELS[dilim.asset_class],
      value: dilim.value,
      formattedValue: formatTRY(dilim.value),
      returnPct: weightedClassReturnPct(dilim.asset_class, holdings),
      weightPct: dilim.percent,
      icon: id,
    };
  });
}

// ---------------------------------------------------------------------------
// Pozisyonlar
// ---------------------------------------------------------------------------

/**
 * `asset_metrics[]`i sembole indeksler — `toHolding` sembol bazında O(1)
 * arasın diye. `risk === null` (istek düştü) ya da hiç varlığı yoksa boş
 * `Map` döner, çağıran taraf ekstra dallanmaya gerek duymaz.
 */
function riskMetricsBySymbol(risk: ApiRiskAssessment | null): Map<string, ApiAssetRiskMetrics> {
  const harita = new Map<string, ApiAssetRiskMetrics>();
  if (risk === null) return harita;
  for (const varlik of risk.metrics.asset_metrics) harita.set(varlik.asset_symbol, varlik);
  return harita;
}

/**
 * Alım işlemlerini sembole göre gruplar — `toHolding`'in "Getiri Detayları"
 * panelinde gösterdiği HAM alış geçmişi için (bkz. HoldingReturnDetail.tsx).
 *
 * Backend'de kalan-adet bazlı parti/lot takibi (FIFO/LIFO) YOK (bilerek
 * kapsam dışı, bkz. ledger_service.py) — bu yüzden burada yalnızca "buy"
 * işlemleri, satışlarla düzeltilmeden, olduğu gibi listeleniyor. Yani bir
 * enstrümanda kısmi satış olduysa bu liste GERÇEKTE elde kalandan fazla
 * gösterebilir; panel bunu açıkça belirtiyor (AK 5.5 — sessizce yanıltmaz).
 * `price` alanı `null` olan satırlar (birim maliyet hesaplanamaz) atlanır.
 */
function buyTransactionsBySymbol(
  transactions: ApiTransactionList | null,
): Map<string, ApiTransactionRow[]> {
  const harita = new Map<string, ApiTransactionRow[]>();
  if (transactions === null) return harita;
  for (const t of transactions.transactions) {
    if (t.type !== "buy" || t.symbol === null || t.price === null) continue;
    const liste = harita.get(t.symbol) ?? [];
    liste.push(t);
    harita.set(t.symbol, liste);
  }
  return harita;
}

function lotsFromBuys(buys: ApiTransactionRow[]): HoldingLot[] {
  return buys
    .map((t, i): HoldingLot => ({
      id: `${t.symbol}-${t.transaction_date}-${i}`,
      purchaseDate: t.transaction_date,
      quantity: t.quantity,
      // price/currency cinsinden; TL karşılığı için işlem anındaki kur.
      unitCost: (t.price as number) * t.fx_rate_to_try,
    }))
    // En yeni alım en üstte — bir işlem geçmişi listesi gibi okunsun diye.
    .sort((a, b) => b.purchaseDate.localeCompare(a.purchaseDate));
}

function toHolding(
  h: ApiHoldingRow,
  riskBySymbol: Map<string, ApiAssetRiskMetrics>,
  buysBySymbol: Map<string, ApiTransactionRow[]>,
): Holding {
  const unitLabel = unitLabelFor(h.asset_class, h.currency);
  // Risk seviyesi `/holdings`TEN DEĞİL: bu uçta `risk_level` alanı hiç yok.
  // Kaynağı `/api/risk/{user_id}` — `metrics.asset_metrics[]`, sembole göre
  // burada eşleniyor. Eşleşme yoksa (nakit kalemi, risk isteği düştü, ya da
  // o varlığın kendi geçmişi yetersiz — asset_metrics'te satırı olsa bile
  // risk_level'ı null olabilir) `null` kalır, HoldingsTable "—" gösterir.
  const riskVarlik = riskBySymbol.get(h.symbol);
  const risk = riskVarlik?.risk_level ? RISK_LEVEL_LABELS[riskVarlik.risk_level] : null;
  const riskOrdinal = riskVarlik?.risk_level ? RISK_LEVEL_ORDINALS[riskVarlik.risk_level] : null;

  return {
    id: h.symbol,
    name: h.name,
    assetClass: ASSET_CLASS_LABELS[h.asset_class],
    assetClassId: ASSET_CLASS_IDS[h.asset_class],
    quantity: formatQuantityByUnit(h.quantity, unitLabel),
    value: h.market_value_try ?? 0,
    formattedValue: h.price_missing ? "—" : formatTRY(h.market_value_try ?? 0),
    returnPct: h.price_missing ? null : h.unrealized_pnl_percent,
    risk,
    riskOrdinal,
    currentUnitPrice: h.current_price_try ?? 0,
    unitLabel,
    // Ham alış geçmişi — bkz. buyTransactionsBySymbol/lotsFromBuys. Kalan-adet
    // bazlı DEĞİL (backend'de yok); satır tıklaması listede en az bir alım
    // varsa açık (bkz. HoldingsTable.tsx).
    lots: lotsFromBuys(buysBySymbol.get(h.symbol) ?? []),
  };
}

export function toHoldings(
  holdings: ApiHoldingsValuation | null,
  risk: ApiRiskAssessment | null,
  transactions: ApiTransactionList | null = null,
): Holding[] {
  if (holdings === null) return [];
  const riskBySymbol = riskMetricsBySymbol(risk);
  const buysBySymbol = buyTransactionsBySymbol(transactions);
  return holdings.holdings.map((h) => toHolding(h, riskBySymbol, buysBySymbol));
}

// ---------------------------------------------------------------------------
// Bileşim
// ---------------------------------------------------------------------------

export interface PortfolioPageSources {
  summary: ApiPortfolioSummary;
  holdings: ApiHoldingsValuation | null;
  /** Yalnızca Pozisyonlar tablosundaki risk sütunu için (bkz. toHolding). Düşerse `null` — tablo diğer her şeyle birlikte çizilir, sadece risk "—" kalır. */
  risk: ApiRiskAssessment | null;
  /** Yalnızca Getiri Detayları panelindeki ham alış geçmişi için (bkz. lotsFromBuys). Düşerse `null` — satırlar tıklanamaz kalır, başka hiçbir alan etkilenmez. */
  transactions: ApiTransactionList | null;
}

export function toPortfolioPageData(kaynak: PortfolioPageSources): PortfolioPageData {
  return {
    assetClasses: toAssetClassSummaries(kaynak.summary, kaynak.holdings),
    holdings: toHoldings(kaynak.holdings, kaynak.risk, kaynak.transactions),
    // Kaynağı yok (bkz. PR planı) — PortfolioPage zaten bunu render etmiyor
    // (RiskSummaryCard bağlı değil), boş dizi uydurmadan daha doğru.
    riskSummary: [],
    instrumentCount: kaynak.summary.holdings_count,
    assetClassCount: kaynak.summary.allocation.length,
  };
}
