import { describe, expect, it } from "vitest";
import type { ApiRiskAssessment } from "@/api/risk";
import {
  toAssetRows,
  toContributions,
  toDiversification,
  toOverview,
  toRiskPageData,
  toSharpe,
  toValueAtRisk,
} from "./risk";

/**
 * Risk adapter testleri.
 *
 * Sabitler gerçek backend'e (`/api/risk/{user_id}`) canlı istek atılarak
 * doğrulandı (demo kullanıcı, 2026-08-26) — docs/API.md'nin örnek JSON'u
 * eksikti (category_metrics/asset_metrics/herfindahl_index gibi alanlar
 * dokümanda hiç yoktu), bu yüzden burada gerçek yanıttan alındı.
 */

const RISK: ApiRiskAssessment = {
  user_id: "u1",
  as_of: "2026-07-31",
  risk_profile: "conservative",
  risk_profile_source: "user",
  risk_survey_score: null,
  total_value: 1_569_468.64,
  risk_level: "very_low",
  is_within_profile: true,
  metrics: {
    annualized_volatility_percent: 4.28,
    max_drawdown_percent: 4.38,
    category_metrics: [
      { asset_class: "stock", weight_percent: 8.29, annualized_volatility_percent: 32.46, risk_contribution_percent: 54.08 },
      { asset_class: "precious_metal", weight_percent: 8.35, annualized_volatility_percent: 14.2, risk_contribution_percent: 20.91 },
      { asset_class: "currency", weight_percent: 11.87, annualized_volatility_percent: 8.89, risk_contribution_percent: 15.1 },
      { asset_class: "bond", weight_percent: 16.72, annualized_volatility_percent: 4.44, risk_contribution_percent: 9.65 },
      { asset_class: "cash", weight_percent: 54.77, annualized_volatility_percent: 0.28, risk_contribution_percent: 0.26 },
    ],
    asset_metrics: [
      { asset_symbol: "PPF", asset_class: "cash", weight_percent: 24.17, annualized_volatility_percent: 0.64, risk_level: "very_low" },
      { asset_symbol: "MEVDUAT-V", asset_class: "cash", weight_percent: 18.06, annualized_volatility_percent: 0.0, risk_level: "very_low" },
      { asset_symbol: "THYAO", asset_class: "stock", weight_percent: 8.29, annualized_volatility_percent: 32.46, risk_level: "high" },
    ],
    diversification_ratio: 1.36,
    value_at_risk_try: 6968.01,
    value_at_risk_percent: 0.44,
    value_at_risk_confidence: 95.0,
    value_at_risk_horizon_days: 1,
    sharpe_ratio: -6.74,
    risk_free_rate_percent: 37.0,
    risk_free_rate_is_live: false,
    max_asset_weight_percent: 24.17,
    max_asset_symbol: "PPF",
    max_class_weight_percent: 54.77,
    max_class: "cash",
    herfindahl_index: 0.1646,
    holdings_count: 8,
    asset_class_count: 5,
    price_points_used: 260,
  },
  warnings: [],
  disclaimer: "Bu bir yatırım tavsiyesi değildir.",
};

describe("toOverview", () => {
  it("is_within_profile true iken uyum cümlesi kurar", () => {
    const o = toOverview(RISK);
    expect(o.profileLabel).toBe("Korumacı");
    expect(o.levelLabel).toBe("Çok Düşük");
    expect(o.isWithinProfile).toBe(true);
    expect(o.verdict).toContain("Korumacı profilinize uygun");
  });

  it("is_within_profile false iken 'üzerinde' der", () => {
    const o = toOverview({ ...RISK, is_within_profile: false });
    expect(o.verdict).toContain("profilinizin üzerinde");
  });

  it("risk_level null iken hesaplanamadı der, uydurmaz", () => {
    const o = toOverview({ ...RISK, risk_level: null, is_within_profile: null });
    expect(o.levelLabel).toBeNull();
    expect(o.verdict).toContain("hesaplanamadı");
  });
});

describe("toContributions", () => {
  it("kategorileri risk katkısına göre BÜYÜKTEN KÜÇÜĞE sıralar", () => {
    const c = toContributions(RISK, false);
    expect(c.map((x) => x.id)).toEqual(["stocks", "precious", "fx", "bond", "cash"]);
    expect(c[0].riskContributionPct).toBe(54.08);
  });

  it("açık/koyu tema paletinden doğru rengi seçer", () => {
    const acik = toContributions(RISK, false);
    const koyu = toContributions(RISK, true);
    const acikHisse = acik.find((x) => x.id === "stocks")!;
    const koyuHisse = koyu.find((x) => x.id === "stocks")!;
    expect(acikHisse.color).not.toBe(koyuHisse.color);
  });
});

describe("toDiversification", () => {
  it("canlı veriyle birebir eşleşir", () => {
    const d = toDiversification(RISK);
    expect(d.herfindahlIndex).toBe(0.1646);
    expect(d.diversificationRatio).toBe(1.36);
    expect(d.maxClassWeightPct).toBe(54.77);
    expect(d.maxClassLabel).toBe("Nakit");
  });

  it("max_class null iken maxClassLabel de null olur, uydurmaz", () => {
    const d = toDiversification({ ...RISK, metrics: { ...RISK.metrics, max_class: null } });
    expect(d.maxClassLabel).toBeNull();
  });
});

describe("toAssetRows", () => {
  it("her varlık için sembol, sınıf etiketi ve risk seviyesini eşler", () => {
    const rows = toAssetRows(RISK);
    expect(rows).toHaveLength(3);
    const thyao = rows.find((r) => r.symbol === "THYAO")!;
    expect(thyao.assetClassLabel).toBe("Hisse Senedi");
    expect(thyao.riskLevelLabel).toBe("Yüksek");
    expect(thyao.riskLevelOrdinal).toBe(6);
  });

  it("risk_level null olan varlıkta '—' yerine null döner (uydurmaz)", () => {
    const rows = toAssetRows({
      ...RISK,
      metrics: {
        ...RISK.metrics,
        asset_metrics: [
          { asset_symbol: "YENI", asset_class: "stock", weight_percent: 1, annualized_volatility_percent: null, risk_level: null },
        ],
      },
    });
    expect(rows[0].riskLevelLabel).toBeNull();
    expect(rows[0].riskLevelOrdinal).toBeNull();
  });
});

describe("toValueAtRisk", () => {
  it("gün sayısından ufuk etiketini üretir — sabit '1 aylık' metni YOK", () => {
    const v = toValueAtRisk(RISK);
    expect(v.horizonLabel).toBe("1 günlük ufukta");
    expect(v.amount).toBe(6968.01);
    expect(v.confidencePct).toBe(95);
  });

  it("value_at_risk_try null iken '—' gösterir", () => {
    const v = toValueAtRisk({ ...RISK, metrics: { ...RISK.metrics, value_at_risk_try: null } });
    expect(v.formattedAmount).toBe("—");
    expect(v.amount).toBeNull();
  });
});

describe("toSharpe", () => {
  it("sayıyı olduğu gibi taşır, 'İyi/Kötü' gibi bir yargı ÜRETMEZ", () => {
    const s = toSharpe(RISK);
    expect(s.value).toBe(-6.74);
    expect(s).not.toHaveProperty("rating");
    expect(s.note).toContain("%37");
  });
});

describe("toRiskPageData", () => {
  it("warnings'i olduğu gibi taşır, yapılandırmaz", () => {
    const withWarning = { ...RISK, warnings: ["CEYREK için sınırlı fiyat geçmişi."] };
    const data = toRiskPageData(withWarning, false);
    expect(data.warnings).toEqual(["CEYREK için sınırlı fiyat geçmişi."]);
  });
});
