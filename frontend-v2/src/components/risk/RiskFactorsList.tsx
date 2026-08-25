import type { RiskFactor } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { ArrowUpIcon, MinusIcon } from "@/components/icons";
import { useCountUp } from "@/hooks/useCountUp";
import { DANGER, INK_FAINT, INK_SOFT } from "@/utils/colors";

interface RiskFactorsListProps {
  factors: RiskFactor[];
}

function RiskFactorItem({ f }: { f: RiskFactor }) {
  const animatedValue = useCountUp(f.value, 0, 950);
  const diff = f.value - f.target;
  const isFar = Math.abs(diff) >= 15;
  const diffText = diff === 0 ? "Hedefte" : `Hedeften ${diff > 0 ? "+" : ""}${diff} puan ${diff > 0 ? "üstte" : "altta"}`;
  const isUp = f.color === DANGER;
  const Icon = isUp ? ArrowUpIcon : MinusIcon;

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="flex items-center gap-1.5 text-[13.5px] font-semibold text-ink-soft">
          {f.label}
          <span style={{ color: isUp ? DANGER : INK_FAINT }}>
            <Icon size={12} />
          </span>
        </span>
        <span
          className="font-display text-[15px] font-bold"
          style={{ color: f.color === "#C7CBD4" ? INK_SOFT : f.color }}
        >
          {Math.round(animatedValue)}
        </span>
      </div>
      <div className="relative h-[7px] overflow-hidden rounded-full bg-line2">
        <div className="h-full rounded-full" style={{ width: `${animatedValue}%`, background: f.color }} />
      </div>
      <p className="m-0 mt-[7px] flex items-center gap-1.5 text-[12.5px] text-ink-faint">
        {f.note}
        {isFar && (
          <span title={diffText} className="text-danger">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#E63946">
              <circle cx="12" cy="12" r="10" />
              <rect x="11" y="6" width="2" height="7" fill="#fff" />
              <rect x="11" y="15" width="2" height="2" fill="#fff" />
            </svg>
          </span>
        )}
      </p>
    </div>
  );
}

export function RiskFactorsList({ factors }: RiskFactorsListProps) {
  return (
    <Card className="p-6">
      <h2 className="font-display m-0 mb-1 text-[17px] font-semibold">Skoru Oluşturan Bileşenler</h2>
      <p className="m-0 mb-[22px] text-[13px] text-ink-faint">Her bileşen 100 üzerinden değerlendirildi</p>
      <div className="flex flex-col gap-[19px]">
        {factors.map((f) => (
          <RiskFactorItem key={f.id} f={f} />
        ))}
      </div>
    </Card>
  );
}
