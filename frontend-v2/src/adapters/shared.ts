import type { ApiAssetClass } from "@/api/portfolio";
import type { ApiRiskAssessment, ApiRiskLevel } from "@/api/risk";
import type { AssetClassId } from "@/types/finance";

/**
 * Backend'in 5 varlık sınıfı ↔ arayüz paletindeki kimlikler/etiketler.
 *
 * `adapters/dashboard.ts` ve `adapters/portfolio.ts` arasında paylaşılıyor —
 * ikisi de aynı backend enum'unu aynı Türkçe etikete/kimliğe çevirmeli, aksi
 * halde iki ekranda aynı varlık sınıfı farklı isimle görünür.
 *
 * Arayüz paletinde ayrıca `crypto` var; backend'de karşılığı YOK ve adapter'lar
 * bunu asla üretmez. Palet dosyasında durması zararsız (ileride sınıf
 * eklenirse rengi hazır), ama buradan çıkmadığı sürece ekranda görünmez.
 */
export const ASSET_CLASS_IDS: Record<ApiAssetClass, AssetClassId> = {
  stock: "stocks",
  precious_metal: "precious",
  currency: "fx",
  bond: "bond",
  cash: "cash",
};

export const ASSET_CLASS_LABELS: Record<ApiAssetClass, string> = {
  stock: "Hisse Senedi",
  precious_metal: "Kıymetli Madenler",
  currency: "Döviz",
  // "Tahvil" DEĞİL: bu sınıfta doğrudan devlet tahvili yok, hepsi TEFAS
  // borçlanma araçları fonu (ve bir para piyasası fonu).
  bond: "Borçlanma Araçları",
  cash: "Nakit",
};

/**
 * Açık tema varlık sınıfı renkleri — Dashboard'daki Varlık Dağılımı donut'u
 * ve `adapters/risk.ts`'teki risk katkısı çubukları aynı buradan okur, iki
 * ekran arasında renk sapması olmasın diye. Koyu tema paleti ayrı bir
 * kaynaktan (`data/assetColors.ts`teki `DARK_ASSET_CLASS_COLORS`) geliyor —
 * koyu temada kontrast için farklı bir ölçek kullanılıyor.
 */
export const LIGHT_ASSET_CLASS_COLORS: Record<AssetClassId, { color: string; highlight: string }> = {
  stocks: { color: "#1E3A8A", highlight: "#3B82F6" },
  precious: { color: "#B45309", highlight: "#F59E0B" },
  fx: { color: "#047857", highlight: "#10B981" },
  bond: { color: "#5B21B6", highlight: "#8B5CF6" },
  cash: { color: "#475569", highlight: "#94A3B8" },
  crypto: { color: "#334155", highlight: "#64748B" },
};

/** 7 kademeli risk seviyesinin Türkçe karşılığı. Tek kaynak — `dashboard.ts`
 * ve `risk.ts` adapter'ları aynı etiketleri kullanmalı. */
export const RISK_LEVEL_LABELS: Record<ApiRiskLevel, string> = {
  very_low: "Çok Düşük",
  low: "Düşük",
  low_medium: "Düşük-Orta",
  medium: "Orta",
  medium_high: "Orta-Yüksek",
  high: "Yüksek",
  very_high: "Çok Yüksek",
};

/**
 * Kademenin SIRA numarası (1-7). `RISK_LEVEL_LABELS` ile aynı sırayı izler;
 * ikisi ayrıştığında gösterge yanlış rengi verir, bu yüzden yan yana duruyorlar.
 */
export const RISK_LEVEL_ORDINALS: Record<ApiRiskLevel, number> = {
  very_low: 1,
  low: 2,
  low_medium: 3,
  medium: 4,
  medium_high: 5,
  high: 6,
  very_high: 7,
};

export const RISK_PROFILE_LABELS: Record<ApiRiskAssessment["risk_profile"], string> = {
  conservative: "Korumacı",
  balanced: "Dengeli",
  growth: "Büyüme",
  aggressive: "Agresif",
};
