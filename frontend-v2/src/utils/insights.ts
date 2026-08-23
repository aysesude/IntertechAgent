import type {
  DashboardData,
  Holding,
  PortfolioPageData,
  TargetVsActualRow,
} from "@/types/finance";
import type { Insight, InsightSeverity } from "@/types/insight";
import { formatPct, formatSignedTRY, formatTRY } from "@/utils/format";
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

const SEVERITY_RANK: Record<InsightSeverity, number> = {
  uyari: 0,
  olumlu: 1,
  bilgi: 2,
};

/** K1 — hedef vs gerçekleşen ağırlık sapması, sapan her satır için bir içgörü. */
function buildWeightDeviationInsights(
  targetVsActual: TargetVsActualRow[],
  totalValue: number
): Insight[] {
  return targetVsActual
    .filter((row) => Math.abs(row.diff) >= WEIGHT_DEVIATION_LIMIT)
    .map((row) => {
      const amountTRY = (totalValue * row.diff) / 100;
      const over = row.diff > 0;
      const title = over
        ? `${row.label} ağırlığın hedefini aştı`
        : `${row.label} ağırlığın hedefin altında kaldı`;
      const body =
        `Mevcut ağırlık %${row.actualPct}, hedef %${row.targetPct}. Hedeften ${Math.abs(row.diff)} puan sapma, ` +
        `yaklaşık ${formatTRY(Math.abs(amountTRY))} tutarında.`;

      return {
        id: `k1-agirlik-sapmasi-${row.id}`,
        severity: "uyari",
        agent: "portfoy",
        title,
        body,
        amountTRY,
        evidence: [
          { label: "Mevcut ağırlık", value: `%${row.actualPct}` },
          { label: "Hedef ağırlık", value: `%${row.targetPct}` },
          { label: "Sapma", value: `${over ? "+" : ""}${row.diff} puan` },
          { label: "Parasal etki", value: formatSignedTRY(amountTRY) },
        ],
      } satisfies Insight;
    });
}

/** K2 — nakit ağırlığı üst sınırın üzerindeyse, enflasyon karşısındaki aylık reel kaybı bildir. */
function buildCashSurplusInsight(dashboard: DashboardData): Insight | null {
  const cash = dashboard.allocation.find((slice) => slice.name === "Nakit");
  if (!cash || cash.pct <= CASH_LIMIT_PCT) return null;

  const monthlyLoss = (cash.value * MONTHLY_INFLATION_PCT) / 100;

  return {
    id: "k2-nakit-fazlasi",
    severity: "uyari",
    agent: "portfoy",
    title: "Nakit ağırlığın gereğinden fazla",
    body:
      `Nakit ağırlığın %${cash.pct}, referans üst sınır %${CASH_LIMIT_PCT}. Enflasyon karşısında ` +
      `aylık yaklaşık ${formatTRY(monthlyLoss)} reel kayıp oluşuyor.`,
    amountTRY: -monthlyLoss,
    evidence: [
      { label: "Nakit ağırlığı", value: `%${cash.pct}` },
      { label: "Referans sınır", value: `%${CASH_LIMIT_PCT}` },
      { label: "Nakit tutarı", value: formatTRY(cash.value) },
      { label: "Aylık enflasyon varsayımı", value: `%${MONTHLY_INFLATION_PCT}` },
      { label: "Tahmini aylık reel kayıp", value: formatTRY(monthlyLoss) },
    ],
  };
}

/** K3 — tek bir varlığın portföy içindeki payı sınırın üzerindeyse, en yoğunlaşanı bildir. */
function buildSingleHoldingConcentrationInsight(
  holdings: Holding[],
  totalValue: number
): Insight | null {
  if (totalValue <= 0 || holdings.length === 0) return null;

  const withWeight = holdings.map((h) => ({ holding: h, weightPct: (h.value / totalValue) * 100 }));
  const worst = withWeight.reduce((a, b) => (b.weightPct > a.weightPct ? b : a));
  if (worst.weightPct <= SINGLE_HOLDING_LIMIT_PCT) return null;

  const weightLabel = worst.weightPct.toFixed(1).replace(".", ",");

  return {
    id: `k3-tek-varlik-yogunlasmasi-${worst.holding.id}`,
    severity: "uyari",
    agent: "risk",
    title: `${worst.holding.name} portföyünde yoğunlaşma yaratıyor`,
    body:
      `${worst.holding.name}, portföyünün %${weightLabel}'ini oluşturuyor — sınır %${SINGLE_HOLDING_LIMIT_PCT}. ` +
      `Tek bir varlıkta bu düzeyde yoğunlaşma çeşitlendirmeyi azaltır.`,
    amountTRY: worst.holding.value,
    evidence: [
      { label: "Varlık", value: worst.holding.name },
      { label: "Portföy içindeki payı", value: `%${weightLabel}` },
      { label: "Sınır", value: `%${SINGLE_HOLDING_LIMIT_PCT}` },
      { label: "Pozisyon tutarı", value: formatTRY(worst.holding.value) },
    ],
  };
}

/** K4 — risk skoru hedef bandın dışındaysa, hangi yönde olduğunu bildir. */
function buildRiskScoreBandInsight(dashboard: DashboardData): Insight | null {
  const score = dashboard.summary.riskScore;
  // Risk skoru artık opsiyonel: risk v2 kompozit skoru kaldırdı ve adapter
  // bu alanı doldurmuyor. Kaynağı yokken kural sessizce atlanır — uydurma
  // bir eşikle içgörü üretmektense hiç üretmemek doğru (CLAUDE.md §4).
  if (score === undefined) return null;
  if (score >= RISK_BAND.low && score <= RISK_BAND.high) return null;

  const below = score < RISK_BAND.low;
  const title = below ? "Risk skorun hedef bandın altında" : "Risk skorun hedef bandın üzerinde";
  const body = below
    ? `Risk skorun ${score}/100, hedef bant ${RISK_BAND.low}–${RISK_BAND.high}. Profiline göre gereğinden temkinli bir portföy taşıyor olabilirsin.`
    : `Risk skorun ${score}/100, hedef bant ${RISK_BAND.low}–${RISK_BAND.high}. Profiline göre beklenenden daha fazla risk taşıyor olabilirsin.`;

  return {
    id: "k4-risk-skoru-bandi",
    severity: "uyari",
    agent: "risk",
    title,
    body,
    evidence: [
      { label: "Risk skoru", value: `${score}/100` },
      { label: "Hedef bant", value: `${RISK_BAND.low}–${RISK_BAND.high}` },
    ],
  };
}

/** K5 — en zayıf performans gösteren pozisyon (eşik altındakiler arasında). */
function buildWeakPerformanceInsight(holdings: Holding[]): Insight | null {
  const candidates = holdings.filter((h) => h.returnPct <= WEAK_RETURN_PCT);
  if (candidates.length === 0) return null;

  const worst = candidates.reduce((a, b) => (b.returnPct < a.returnPct ? b : a));
  const impact = (worst.value * worst.returnPct) / 100;

  return {
    id: `k5-zayif-performans-${worst.id}`,
    severity: "uyari",
    agent: "portfoy",
    title: `${worst.name} zayıf performans gösteriyor`,
    body:
      `${worst.name}, ${formatPct(worst.returnPct)} getiriyle portföydeki en zayıf pozisyon. ` +
      `Bu yaklaşık ${formatSignedTRY(impact)} değer kaybı anlamına geliyor.`,
    amountTRY: impact,
    evidence: [
      { label: "Varlık", value: worst.name },
      { label: "Getiri", value: formatPct(worst.returnPct) },
      { label: "Pozisyon tutarı", value: formatTRY(worst.value) },
      { label: "Tahmini etki", value: formatSignedTRY(impact) },
    ],
  };
}

/** K6 — en güçlü performans gösteren pozisyon (eşik üstündekiler arasında). */
function buildStrongPerformanceInsight(holdings: Holding[]): Insight | null {
  const candidates = holdings.filter((h) => h.returnPct >= STRONG_RETURN_PCT);
  if (candidates.length === 0) return null;

  const best = candidates.reduce((a, b) => (b.returnPct > a.returnPct ? b : a));
  const impact = (best.value * best.returnPct) / 100;

  return {
    id: `k6-guclu-performans-${best.id}`,
    severity: "olumlu",
    agent: "portfoy",
    title: `${best.name} güçlü getiri sağladı`,
    body:
      `${best.name}, ${formatPct(best.returnPct)} getiriyle portföydeki en güçlü pozisyon. ` +
      `Bu yaklaşık ${formatSignedTRY(impact)} katkı anlamına geliyor.`,
    amountTRY: impact,
    evidence: [
      { label: "Varlık", value: best.name },
      { label: "Getiri", value: formatPct(best.returnPct) },
      { label: "Pozisyon tutarı", value: formatTRY(best.value) },
      { label: "Tahmini etki", value: formatSignedTRY(impact) },
    ],
  };
}

/** K7 — aylık portföy getirisi ile BIST 100 arasındaki fark anlamlıysa bildir. */
function buildBenchmarkGapInsight(dashboard: DashboardData, totalValue: number): Insight | null {
  const aylik = dashboard.periodReturns?.aylik;
  if (!aylik) return null;

  const gap = aylik.returnPct - aylik.benchmarkPct;
  if (gap < BENCHMARK_GAP_PCT && gap > -BENCHMARK_GAP_PCT) return null;

  const outperforming = gap >= BENCHMARK_GAP_PCT;
  const amountTRY = (totalValue * gap) / 100;

  return {
    id: "k7-benchmark-farki",
    severity: outperforming ? "olumlu" : "uyari",
    agent: "piyasa",
    title: outperforming ? "Portföyün BIST 100'ü geride bıraktı" : "Portföyün BIST 100'ün gerisinde kaldı",
    body:
      `Bu ay portföy getirin ${formatPct(aylik.returnPct)}, BIST 100 ${formatPct(aylik.benchmarkPct)}. ` +
      `Aradaki fark ${formatPct(gap)}, yaklaşık ${formatSignedTRY(amountTRY)}.`,
    amountTRY,
    evidence: [
      { label: "Portföy getirisi (aylık)", value: formatPct(aylik.returnPct) },
      { label: "BIST 100 (aylık)", value: formatPct(aylik.benchmarkPct) },
      { label: "Fark", value: formatPct(gap) },
    ],
  };
}

/** K8 — döviz ağırlığı referans sınırın üzerindeyse bilgilendir. */
function buildFxExposureInsight(dashboard: DashboardData): Insight | null {
  const fx = dashboard.allocation.find((slice) => slice.name === "Döviz");
  if (!fx || fx.pct <= FX_LIMIT_PCT) return null;

  return {
    id: "k8-doviz-acikligi",
    severity: "bilgi",
    agent: "risk",
    title: "Döviz ağırlığın dikkat çekici seviyede",
    body:
      `Döviz varlıkların portföyünün %${fx.pct}'ini oluşturuyor, referans üst sınır %${FX_LIMIT_PCT}. ` +
      `Bu, kur hareketlerine duyarlılığının arttığı anlamına gelir.`,
    amountTRY: fx.value,
    evidence: [
      { label: "Döviz ağırlığı", value: `%${fx.pct}` },
      { label: "Referans sınır", value: `%${FX_LIMIT_PCT}` },
      { label: "Döviz tutarı", value: formatTRY(fx.value) },
    ],
  };
}

/**
 * Dashboard ve portföy verisinden deterministik içgörü listesi üretir.
 * Aynı girdi her zaman aynı çıktıyı verir — rastgelelik veya dış çağrı yok.
 * Sıralama: önce severity (uyari > olumlu > bilgi), sonra |amountTRY| büyükten
 * küçüğe. En fazla MAX_INSIGHTS kadar içgörü döner.
 */
export function buildInsights(dashboard: DashboardData, portfolio: PortfolioPageData): Insight[] {
  const totalValue = dashboard.summary.totalValue;

  const insights: Insight[] = [
    ...buildWeightDeviationInsights(portfolio.targetVsActual, totalValue),
    buildCashSurplusInsight(dashboard),
    buildSingleHoldingConcentrationInsight(portfolio.holdings, totalValue),
    buildRiskScoreBandInsight(dashboard),
    buildWeakPerformanceInsight(portfolio.holdings),
    buildStrongPerformanceInsight(portfolio.holdings),
    buildBenchmarkGapInsight(dashboard, totalValue),
    buildFxExposureInsight(dashboard),
  ].filter((insight): insight is Insight => insight !== null);

  return insights
    .sort((a, b) => {
      const severityDiff = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
      if (severityDiff !== 0) return severityDiff;
      return Math.abs(b.amountTRY ?? 0) - Math.abs(a.amountTRY ?? 0);
    })
    .slice(0, MAX_INSIGHTS);
}
