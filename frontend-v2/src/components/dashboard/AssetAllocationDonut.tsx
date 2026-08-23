import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { ChevronDown } from "lucide-react";
import type { AssetAllocationSlice } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { INK, INK_FAINT, INK_SOFT, SURFACE_ELEVATED } from "@/utils/colors";
import { DARK_ASSET_CLASS_COLORS } from "@/data/assetColors";
import { useTheme } from "@/context/ThemeContext";

interface AssetAllocationDonutProps {
  slices: AssetAllocationSlice[];
  instrumentCount: number;
  assetClassCount: number;
}

export function AssetAllocationDonut({ slices, instrumentCount, assetClassCount }: AssetAllocationDonutProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const toggleSelected = (i: number) => setSelected((prev) => (prev === i ? null : i));

  // Koyu temada Portfolio sayfasıyla (AssetClassCards) aynı paletten okunuyor
  // (bkz. src/data/assetColors.ts) — light modda slice'ın kendi renkleri
  // aynen kullanılıyor.
  const sliceColor = (slice: AssetAllocationSlice) => (isDark ? DARK_ASSET_CLASS_COLORS[slice.id].color : slice.color);
  const sliceHighlight = (slice: AssetAllocationSlice) =>
    isDark ? DARK_ASSET_CLASS_COLORS[slice.id].highlight : slice.highlightColor;

  return (
    <Card className="p-6">
      <h2 className="font-display m-0 mb-1 text-[17px] font-semibold">Varlık Dağılımı</h2>
      <p className="m-0 mb-2 text-[13px] text-ink-faint">
        {assetClassCount} sınıf · {instrumentCount} enstrüman · bir dilime tıkla, alt türleri gör
      </p>

      <div className="my-1.5 grid place-items-center">
        <div className="aspect-square w-full max-w-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={slices}
                dataKey="pct"
                nameKey="name"
                innerRadius="52%"
                outerRadius="100%"
                paddingAngle={1}
                stroke={SURFACE_ELEVATED}
                strokeWidth={2}
                isAnimationActive={false}
                onMouseEnter={(_, i) => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                onClick={(_, i) => toggleSelected(i)}
              >
                {slices.map((slice, i) => (
                  <Cell
                    key={slice.name}
                    fill={hovered === i ? sliceHighlight(slice) : sliceColor(slice)}
                    opacity={hovered === null || hovered === i ? 1 : 0.32}
                    stroke={selected === i ? INK : SURFACE_ELEVATED}
                    style={{ cursor: "pointer", transition: "opacity .15s ease-out, fill .15s ease-out" }}
                  />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="flex flex-col gap-[11px]">
        {slices.map((slice, i) => {
          const isHovered = hovered === i;
          const isSelected = selected === i;
          const isNotHeld = slice.value === 0;
          const expandable = slice.subcategories.length > 0;

          const rowContent = (
            <>
              <span className="h-[9px] w-[9px] shrink-0 rounded-[3px]" style={{ background: sliceColor(slice) }} />
              <span
                className="flex-1 text-[16px] transition-colors"
                style={{ color: isNotHeld ? INK_FAINT : isHovered || isSelected ? INK : INK_SOFT, fontWeight: isHovered || isSelected ? 600 : 500 }}
              >
                {slice.name}
                {isNotHeld && <span className="ml-1.5 text-[11px] font-normal text-ink-faint">(portföyde yok)</span>}
              </span>
              <span className={isNotHeld ? "font-semibold text-ink-faint" : "font-semibold"}>{slice.formattedValue}</span>
              <span className="w-[38px] text-right text-ink-faint">{slice.pct}%</span>
              {expandable && (
                <ChevronDown
                  size={15}
                  className="shrink-0 text-ink-faint transition-transform"
                  style={{ transform: isSelected ? "rotate(180deg)" : "rotate(0deg)" }}
                />
              )}
            </>
          );

          return (
            <div key={slice.name} className="-mx-2">
              {expandable ? (
                <button
                  type="button"
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => toggleSelected(i)}
                  aria-expanded={isSelected}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px]"
                >
                  {rowContent}
                </button>
              ) : (
                <div
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px]"
                >
                  {rowContent}
                </div>
              )}

              {isSelected && expandable && (
                <div className="animate-fadeUp ml-[19px] mt-1 flex flex-col gap-1.5 border-l-2 border-line2 py-1 pl-3">
                  {slice.subcategories.map((sub) => (
                    <div key={sub.name} className="flex items-center gap-2.5 text-[12.5px]">
                      <span className="flex-1 text-ink-muted">{sub.name}</span>
                      <span className="font-semibold text-ink-soft">{sub.formattedValue}</span>
                      <span className="w-[34px] text-right text-ink-faint">{sub.pct}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
