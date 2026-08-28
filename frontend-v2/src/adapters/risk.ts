import type { ApiRiskAssessment } from "@/api/risk";
import {
  ASSET_CLASS_IDS,
  ASSET_CLASS_LABELS,
  LIGHT_ASSET_CLASS_COLORS,
  RISK_LEVEL_LABELS,
  RISK_LEVEL_ORDINALS,
  RISK_PROFILE_LABELS,
} from "@/adapters/shared";
import { DARK_ASSET_CLASS_COLORS } from "@/data/assetColors";
import { formatNumberTR, formatTRY } from "@/utils/format";
import type {
  RiskAssetRow,
  RiskCategoryContribution,
  RiskDiversification,
  RiskOverview,
  RiskPageData,
  SharpeRatio,
  ValueAtRisk,
} from "@/types/finance";

/**
 * Backend'in `/api/risk/{user_id}` çıktısını Risk sayfasının görünüm
 * modeline çevirir. `adapters/dashboard.ts`/`portfolio.ts` ile aynı ilke:
 * SAF fonksiyonlar, kaynağı olmayan alan uydurulmaz (AK 5.5).
 *
 * KALDIRILAN KAVRAMLAR — bilerek üretilmiyor:
 * - 0-100 kompozit risk skoru (Risk v2'de kaldırıldı, `docs/API.md`).
 * - Strateji önerileri / senaryolar (ürün kararıyla kapsam dışı).
 */

// ---------------------------------------------------------------------------
// 1. Üst şerit — profil ve genel durum
// ---------------------------------------------------------------------------

export function toOverview(risk: ApiRiskAssessment): RiskOverview {
  const profileLabel = RISK_PROFILE_LABELS[risk.risk_profile];
  const levelLabel = risk.risk_level ? RISK_LEVEL_LABELS[risk.risk_level] : null;
  const level = risk.risk_level ? RISK_LEVEL_ORDINALS[risk.risk_level] : null;

  // `is_within_profile` volatiliteyle BİRLİKTE null gelir (yeterli fiyat
  // geçmişi yoksa) — o durumda tek cümlelik yargı da üretilemez.
  const verdict =
    risk.is_within_profile === null
      ? "Risk seviyesi hesaplanamadı — yeterli fiyat geçmişi yok."
      : risk.is_within_profile
        ? `Ölçülen risk seviyeniz (${levelLabel}), ${profileLabel} profilinize uygun.`
        : `Ölçülen risk seviyeniz (${levelLabel}), ${profileLabel} profilinizin üzerinde.`;

  return { profileLabel, levelLabel, level, isWithinProfile: risk.is_within_profile, verdict };
}

// ---------------------------------------------------------------------------
// 2. Risk nereden geliyor — sınıf bazlı katkı
// ---------------------------------------------------------------------------

export function toContributions(risk: ApiRiskAssessment, darkTheme: boolean): RiskCategoryContribution[] {
  const palet = darkTheme ? DARK_ASSET_CLASS_COLORS : LIGHT_ASSET_CLASS_COLORS;

  return [...risk.metrics.category_metrics]
    .sort((a, b) => (b.risk_contribution_percent ?? -1) - (a.risk_contribution_percent ?? -1))
    .map((c) => {
      const id = ASSET_CLASS_IDS[c.asset_class];
      return {
        id,
        name: ASSET_CLASS_LABELS[c.asset_class],
        weightPct: c.weight_percent,
        volatilityPct: c.annualized_volatility_percent,
        riskContributionPct: c.risk_contribution_percent,
        color: palet[id].color,
        highlightColor: palet[id].highlight,
      };
    });
}

// ---------------------------------------------------------------------------
// 3. Çeşitlendirme
// ---------------------------------------------------------------------------

export function toDiversification(risk: ApiRiskAssessment): RiskDiversification {
  const m = risk.metrics;
  return {
    herfindahlIndex: m.herfindahl_index,
    diversificationRatio: m.diversification_ratio,
    maxClassWeightPct: m.max_class_weight_percent,
    maxClassLabel: m.max_class ? ASSET_CLASS_LABELS[m.max_class] : null,
  };
}

// ---------------------------------------------------------------------------
// 4. Varlık bazlı risk tablosu
// ---------------------------------------------------------------------------

export function toAssetRows(risk: ApiRiskAssessment): RiskAssetRow[] {
  return risk.metrics.asset_metrics.map((a) => ({
    symbol: a.asset_symbol,
    assetClassLabel: ASSET_CLASS_LABELS[a.asset_class],
    weightPct: a.weight_percent,
    volatilityPct: a.annualized_volatility_percent,
    riskLevelLabel: a.risk_level ? RISK_LEVEL_LABELS[a.risk_level] : null,
    riskLevelOrdinal: a.risk_level ? RISK_LEVEL_ORDINALS[a.risk_level] : null,
  }));
}

// ---------------------------------------------------------------------------
// 5. VaR ve Sharpe
// ---------------------------------------------------------------------------

/** Sabit metin DEĞİL — backend'in verdiği ufuk gün sayısından üretilir. */
function formatHorizonLabel(days: number): string {
  return `${days} günlük ufukta`;
}

export function toValueAtRisk(risk: ApiRiskAssessment): ValueAtRisk {
  const m = risk.metrics;
  return {
    amount: m.value_at_risk_try,
    formattedAmount: m.value_at_risk_try === null ? "—" : formatTRY(m.value_at_risk_try),
    confidencePct: m.value_at_risk_confidence,
    horizonLabel: formatHorizonLabel(m.value_at_risk_horizon_days),
  };
}

/**
 * Sharpe'ı bir "İyi/Kötü" yargısına ÇEVİRMEZ — docs/API.md:490'daki uyarı:
 * risksiz faiz oranı yüksek olduğu için düşük volatiliteli portföylerde
 * Sharpe sistematik olarak negatif çıkıyor; bağlamsız gösterilmemeli. `note`
 * bu bağlamı gerçek `risk_free_rate_percent` değeriyle anlatan bir açıklama.
 */
export function toSharpe(risk: ApiRiskAssessment): SharpeRatio {
  const m = risk.metrics;
  const oran = formatNumberTR(m.risk_free_rate_percent, 1);
  return {
    value: m.sharpe_ratio,
    note: `Risksiz faiz oranı şu an %${oran} — bu düzey, düşük volatiliteli portföylerde Sharpe oranını sistematik olarak negatife çekebilir. Bu, portföyün kötü performans gösterdiği anlamına gelmez.`,
  };
}

// ---------------------------------------------------------------------------
// Bileşim
// ---------------------------------------------------------------------------

export function toRiskPageData(risk: ApiRiskAssessment, darkTheme: boolean): RiskPageData {
  return {
    overview: toOverview(risk),
    contributions: toContributions(risk, darkTheme),
    diversification: toDiversification(risk),
    assets: toAssetRows(risk),
    valueAtRisk: toValueAtRisk(risk),
    sharpe: toSharpe(risk),
    // Backend serbest metin döndürüyor — yapılandırılmış alan yok, olduğu
    // gibi taşınıyor.
    warnings: risk.warnings,
  };
}
