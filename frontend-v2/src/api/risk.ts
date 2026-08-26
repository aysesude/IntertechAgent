import { apiGet } from "./client";
import type { ApiAssetClass } from "./portfolio";

/**
 * Risk değerlendirmesi ucunun HAM şekli.
 *
 * `backend/app/schemas/risk.py` ile birebir eşleşir. Hesaplanamayan değerler
 * `null` gelir, `0` değil: yeterli fiyat geçmişi yoksa risk UYDURULMAZ
 * (AK 2.7 / 5.5), sebep `warnings` listesinde döner.
 *
 * `causes` (kök neden teşhisi) ve `scenarios` (yeniden dengeleme simülasyonu)
 * BİLEREK burada tanımlı değil: `scenarios` ürün kararıyla arayüze kapalı
 * (öneri/aksiyon üretmek kapsam dışı — bkz. docs/API.md), `causes` da onunla
 * aynı ailede (yalnızca is_within_profile=false iken dolu, "ne yapmalısın"
 * değil ama yine de bu turda kullanılmıyor). `category_correlation_matrix`
 * da aynı sebeple atlandı — hiçbir ekran onu tüketmiyor.
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

/** Tek bir varlık sınıfı için hesaplanan risk katkısı. */
export interface ApiCategoryRiskMetrics {
  asset_class: ApiAssetClass;
  weight_percent: number;
  annualized_volatility_percent: number | null;
  /** Bu sınıfın portföy VARYANSINA katkısı (RC%, toplam ~1'e yakındır). */
  risk_contribution_percent: number | null;
}

/** Tek bir VARLIĞIN (kategori değil) kendi volatilitesi ve risk etiketi. */
export interface ApiAssetRiskMetrics {
  asset_symbol: string;
  asset_class: ApiAssetClass;
  weight_percent: number;
  /** Yeterli ortak fiyat günü yoksa `null` — tahmini değerle doldurulmaz. */
  annualized_volatility_percent: number | null;
  risk_level: ApiRiskLevel | null;
}

export interface ApiRiskMetrics {
  annualized_volatility_percent: number | null;
  max_drawdown_percent: number | null;
  category_metrics: ApiCategoryRiskMetrics[];
  /** Elde tutulan her varlık için bir kayıt (volatilite hesaplanamasa da). */
  asset_metrics: ApiAssetRiskMetrics[];
  /** DR = (Σ wᵢ×σᵢ) / σ_portföy. 1'e yakınsa çeşitlendirme etkisi zayıf. */
  diversification_ratio: number | null;
  value_at_risk_try: number | null;
  value_at_risk_percent: number | null;
  value_at_risk_confidence: number;
  value_at_risk_horizon_days: number;
  sharpe_ratio: number | null;
  risk_free_rate_percent: number;
  risk_free_rate_is_live: boolean;
  max_asset_weight_percent: number;
  max_asset_symbol: string | null;
  max_class_weight_percent: number;
  max_class: ApiAssetClass | null;
  /** Yoğunlaşma endeksi (Herfindahl-Hirschman), 0-1. */
  herfindahl_index: number;
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
  total_value: number;
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
