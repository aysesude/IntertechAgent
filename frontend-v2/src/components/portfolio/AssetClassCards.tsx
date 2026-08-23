import type { AssetClassSummary } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { ChartLine, ArrowLeftRight, FileText, Banknote, Share2 } from "lucide-react";
import { formatPct } from "@/utils/format";
import { POSITIVE, NEGATIVE, INK_FAINT } from "@/utils/colors";
import { DARK_ASSET_CLASS_COLORS } from "@/data/assetColors";
import { useTheme } from "@/context/ThemeContext";

/** Sade, monoline külçe/altın bar ikonu — lucide-react'te doğrudan karşılığı yok. */
function IngotIcon({ size = 20, strokeWidth = 1.5, className }: { size?: number; strokeWidth?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M5 8h14l2 8H3z" />
      <path d="M7.3 8l1.4 8M16.7 8l-1.4 8" />
    </svg>
  );
}

const ICONS = { stocks: ChartLine, precious: IngotIcon, fx: ArrowLeftRight, bond: FileText, crypto: Share2, cash: Banknote } as const;

// Sabit "#344054" yerine ink-soft token'ı — aynı ton, ama koyu temada
// otomatik olarak açık bir gri-lacivert'e döner (bkz. src/index.css .dark).
const ICON_COLOR = "var(--color-ink-soft)";

// Ağırlık çubuğunun rengi — ikon kutuları kaldırıldı ama progress bar rengi
// (ve tüm diğer renkler) aynen korunuyor.
const ASSET_BAR_COLORS: Record<keyof typeof ICONS, string> = {
  stocks: "#2557E8",
  precious: "#D4A017",
  fx: "#14B8A6",
  bond: "#8B5CF6",
  crypto: "#EA580C",
  cash: "#4B5563",
};

interface AssetClassCardsProps {
  assetClasses: AssetClassSummary[];
}

export function AssetClassCards({ assetClasses }: AssetClassCardsProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  return (
    <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {assetClasses.map((ac) => {
        const Icon = ICONS[ac.icon];
        // Koyu temada Dashboard'daki Varlık Dağılımı donut'uyla aynı kaynaktan
        // (bkz. src/data/assetColors.ts) — iki sayfa arasında renk sapması olmasın.
        const barColor = isDark ? DARK_ASSET_CLASS_COLORS[ac.icon].color : ASSET_BAR_COLORS[ac.icon];
        const positive = ac.returnPct >= 0;
        // Portföyde pozisyonu bulunmayan bir sınıf boş bırakılmak yerine
        // 0/"—" ile açıkça gösterilir (AK-1.2).
        const notHeld = ac.value === 0;
        return (
          <Card key={ac.id} className="p-5">
            <div className="mb-3.5 flex items-center gap-2.5">
              <Icon size={20} strokeWidth={1.5} color={ICON_COLOR} className="shrink-0" />
              <span className="text-[13px] font-semibold text-ink-soft">{ac.name}</span>
            </div>
            <div className={`font-display text-[25px] font-bold tracking-[-0.6px] ${notHeld ? "text-ink-faint" : ""}`}>
              {ac.formattedValue}
            </div>
            <div className="mt-2 text-[13px] font-semibold" style={{ color: notHeld ? INK_FAINT : positive ? POSITIVE : NEGATIVE }}>
              {notHeld ? "Portföyde yok" : formatPct(ac.returnPct)} <span className="font-medium text-ink-faint">· {ac.weightPct}% ağırlık</span>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line2">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${notHeld ? 0 : ac.weightPct}%`, background: notHeld ? "transparent" : barColor }}
              />
            </div>
          </Card>
        );
      })}
    </div>
  );
}
