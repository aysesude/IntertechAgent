import { apiGet } from "./client";

/**
 * Risk değerlendirmesi ucunun HAM şekli.
 *
 * `backend/app/schemas/risk.py` ile birebir eşleşir. Hesaplanamayan değerler
 * `null` gelir, `0` değil: yeterli fiyat geçmişi yoksa risk UYDURULMAZ
 * (AK 2.7 / 5.5), sebep `warnings` listesinde döner.
 */

/** 7 kademeli risk etiketi. Eski 0-100 kompozit skor v2'de kaldırıldı. */
export type ApiRiskLevel =
  | "very_low"
  | "low"
  | "low_medium"
  | "medium"
  | "medium_high"
  | "high"
  | "very_high";

export interface ApiRiskMetrics {
  annualized_volatility_percent: number | null;
  max_drawdown_percent: number | null;
  diversification_ratio: number | null;
  value_at_risk_try: number | null;
  value_at_risk_percent: number | null;
  value_at_risk_confidence: number;
  value_at_risk_horizon_days: number;
  sharpe_ratio: number | null;
  risk_free_rate_percent: number;
  max_asset_weight_percent: number;
  max_asset_symbol: string | null;
  holdings_count: number;
  asset_class_count: number;
  price_points_used: number;
}

export interface ApiRiskAssessment {
  user_id: string;
  as_of: string;
  risk_profile: "conservative" | "balanced" | "growth" | "aggressive";
  risk_profile_source: "user" | "override";
  /**
   * Kullanıcının anket puanı (1-7) — profilin türediği YETKİLİ alan.
   *
   * `null` olabilir: anket doldurulmamıştır ya da sonuç `profile_override`
   * ile hesaplanmıştır (o senaryoda profil kullanıcının beyanı değildir).
   */
  risk_survey_score: number | null;
  risk_level: ApiRiskLevel | null;
  /** Volatilite, profilin beklenen bandının içinde mi? Hesaplanamıyorsa null. */
  is_within_profile: boolean | null;
  metrics: ApiRiskMetrics;
  warnings: string[];
  disclaimer: string;
}

export function fetchRiskAssessment(userId: string) {
  return apiGet<ApiRiskAssessment>(`/api/risk/${userId}`);
}
