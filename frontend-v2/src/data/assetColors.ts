import type { AssetClassId } from "@/types/finance";

// Koyu temada Varlık Dağılımı donut'u (Dashboard) ve varlık sınıfı ağırlık
// çubukları (Portfolio) AYNI paletten okur — tek kaynak, iki sayfa arasında
// renk tutarsızlığı oluşmasın diye.
//
// Önceki palet soğuk bir slate-mavi ölçekti (+ tek bordo dilim); kartlar
// artık çok daha koyu/sıcak bir lacivert zemine (#07111c) ve marka rengi
// bordo/şarap tonuna (--color-brand koyu tema: #C4485A) kaydığı için o
// mavi ölçek bütünle uyumsuz kaldı. Yerine arka plandaki gün batımı
// görseliyle aynı ruhu taşıyan tek yönlü bir "gün batımı → gece" geçişi:
// en büyük/öne çıkan sınıf (Hisse Senedi) marka bordosuna en yakın sıcak
// ton, oradan gül/mora, sonra çiviteye kayıp en küçük/arka plandaki sınıfta
// (Kripto) koyu lacivert kart zeminine yaklaşan en soğuk tona iniyor.
// Marka rengiyle (interaktif eleman) karıştırılmasın diye stocks bilerek
// --color-brand'in AYNISI değil, ona yakın ama ayrışan bir ton.
export const DARK_ASSET_CLASS_COLORS: Record<AssetClassId, { color: string; highlight: string }> = {
  stocks: { color: "#B84A5C", highlight: "#D6667A" },
  precious: { color: "#A85C74", highlight: "#C4788F" },
  fx: { color: "#8E6088", highlight: "#AC7DA6" },
  bond: { color: "#6B5C8A", highlight: "#8878A6" },
  cash: { color: "#4C5580", highlight: "#656F9E" },
  crypto: { color: "#333C60", highlight: "#4A5480" },
};
