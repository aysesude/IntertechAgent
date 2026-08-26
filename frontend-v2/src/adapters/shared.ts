import type { ApiAssetClass } from "@/api/portfolio";
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
