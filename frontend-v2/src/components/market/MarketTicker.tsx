import type { MarketIndicator } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { formatPct } from "@/utils/format";
import { POSITIVE, NEGATIVE, INK_FAINT } from "@/utils/colors";

interface MarketTickerProps {
  indicators: MarketIndicator[];
}

export function MarketTicker({ indicators }: MarketTickerProps) {
  return (
    <Card className="mb-6 grid grid-cols-2 gap-3 px-[22px] py-[18px] sm:grid-cols-3 lg:grid-cols-5">
      {indicators.map((ind) => (
        <div key={ind.id}>
          <div className="text-[11.5px] font-semibold tracking-[.5px] text-ink-faint">{ind.label}</div>
          <div className="mt-[5px] flex items-baseline gap-2">
            <span className="font-display text-[19px] font-bold">{ind.value}</span>
            <span
              className="text-[13px] font-semibold"
              style={{ color: ind.changePct > 0 ? POSITIVE : ind.changePct < 0 ? NEGATIVE : INK_FAINT }}
            >
              {ind.changePct === 0 ? "0,00" : formatPct(ind.changePct)}
            </span>
          </div>
        </div>
      ))}
    </Card>
  );
}
