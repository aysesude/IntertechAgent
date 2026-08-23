import type { AssetClassId } from "@/types/finance";

// Koyu temada Varlık Dağılımı donut'u (Dashboard) ve varlık sınıfı ağırlık
// çubukları (Portfolio) AYNI paletten okur — tek kaynak, iki sayfa arasında
// renk tutarsızlığı oluşmasın diye. Soğuk slate-mavi bir ölçek + tek bir
// bordo dilim (en büyük/öne çıkan sınıf: Hisse Senedi).
export const DARK_ASSET_CLASS_COLORS: Record<AssetClassId, { color: string; highlight: string }> = {
  stocks: { color: "#A34155", highlight: "#C15468" },
  precious: { color: "#8C9AC4", highlight: "#AAB6DE" },
  fx: { color: "#6B7BA8", highlight: "#8896C0" },
  bond: { color: "#4A5A80", highlight: "#647098" },
  cash: { color: "#3A4666", highlight: "#525E82" },
  crypto: { color: "#2E3850", highlight: "#46506A" },
};
