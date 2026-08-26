import type { ReactNode } from "react";
import { Card } from "@/components/common/Card";
import { BRAND, BRAND_BRIGHT } from "@/utils/colors";
import { useTheme } from "@/context/ThemeContext";

interface StatCardProps {
  label: string;
  value: string;
  valueColor?: string;
  footer?: ReactNode;
  progress?: number;
  /**
   * Alt bilgi ile ilerleme çubuğu arasına giren serbest görsel (ör. risk
   * kademesi çubuğu). `progress`'ten ayrı: o marka renkli tek bir doluluk
   * çubuğu çizer, bu ise kartın kendi göstergesini getirir.
   */
  indicator?: ReactNode;
}

export function StatCard({ label, value, valueColor, footer, progress, indicator }: StatCardProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  return (
    <Card className="p-[22px]">
      <div className="mb-3.5 flex min-h-[28px] items-center text-xs font-semibold uppercase tracking-[.4px] text-ink-faint">{label}</div>
      <div className="font-display text-[31px] font-bold tracking-[-0.8px]" style={{ color: valueColor }}>
        {value}
      </div>
      {indicator}
      {footer && <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold">{footer}</div>}
      {progress != null && (
        <div className="mt-3 h-[5px] overflow-hidden rounded-full bg-line2">
          <div
            className="h-full rounded-full"
            style={{
              width: `${progress}%`,
              background: isDark ? BRAND_BRIGHT : `linear-gradient(90deg,${BRAND},#5B8DEE)`,
            }}
          />
        </div>
      )}
    </Card>
  );
}
