import type { ApiAssetClass, ApiHoldingRow, ApiHoldingsValuation, ApiPortfolioSummary } from "@/api/portfolio";
import { ASSET_CLASS_IDS, ASSET_CLASS_LABELS } from "@/adapters/shared";
import { formatQuantityByUnit, formatTRY } from "@/utils/format";
import type { AssetClassSummary, Holding, PortfolioPageData } from "@/types/finance";

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

function toHolding(h: ApiHoldingRow): Holding {
  const unitLabel = unitLabelFor(h.asset_class, h.currency);
  return {
    id: h.symbol,
    name: h.name,
    assetClass: ASSET_CLASS_LABELS[h.asset_class],
    assetClassId: ASSET_CLASS_IDS[h.asset_class],
    quantity: formatQuantityByUnit(h.quantity, unitLabel),
    value: h.market_value_try ?? 0,
    formattedValue: h.price_missing ? "—" : formatTRY(h.market_value_try ?? 0),
    returnPct: h.price_missing ? null : h.unrealized_pnl_percent,
    // Backend `/holdings` henüz enstrüman bazlı risk seviyesi döndürmüyor
    // (`assets.risk_level` DB'de var ama şemaya eklenmedi — bkz. PR planı).
    // Alan gelene kadar `null`; HoldingsTable "—" gösterir.
    risk: null,
    currentUnitPrice: h.current_price_try ?? 0,
    unitLabel,
    // Parti/lot kırılımı için backend ucu yok (bkz. HoldingReturnDetail'deki
    // not) — satır tıklaması bu yüzden devre dışı.
    lots: [],
  };
}

export function toHoldings(holdings: ApiHoldingsValuation | null): Holding[] {
  if (holdings === null) return [];
  return holdings.holdings.map(toHolding);
}

// ---------------------------------------------------------------------------
// Bileşim
// ---------------------------------------------------------------------------

export interface PortfolioPageSources {
  summary: ApiPortfolioSummary;
  holdings: ApiHoldingsValuation | null;
}

export function toPortfolioPageData(kaynak: PortfolioPageSources): PortfolioPageData {
  return {
    assetClasses: toAssetClassSummaries(kaynak.summary, kaynak.holdings),
    holdings: toHoldings(kaynak.holdings),
    // Kaynağı yok (bkz. PR planı) — PortfolioPage zaten bunu render etmiyor
    // (RiskSummaryCard bağlı değil), boş dizi uydurmadan daha doğru.
    riskSummary: [],
    instrumentCount: kaynak.summary.holdings_count,
    assetClassCount: kaynak.summary.allocation.length,
  };
}
