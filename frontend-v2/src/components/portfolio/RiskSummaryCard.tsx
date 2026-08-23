import { ArrowUp, Minus } from "lucide-react";
import type { RiskSummaryRow } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { useCountUp } from "@/hooks/useCountUp";
import { InfoTooltip } from "@/components/common/InfoTooltip";

interface RiskSummaryCardProps {
  rows: RiskSummaryRow[];
}

function formatValuePct(v: number): string {
  return v.toFixed(1).replace(/\.0$/, "").replace(".", ",");
}

function RiskSummaryRowItem({ row, index }: { row: RiskSummaryRow; index: number }) {
  const animatedValue = useCountUp(row.valuePct, index * 70);
  const TrendIcon = row.trend === "up" ? ArrowUp : Minus;

  return (
    <div>
      <div className="mb-[7px] flex justify-between text-[13px]">
        <span className="flex items-center gap-1.5 text-ink-soft">
          {row.label}
          <TrendIcon size={12} strokeWidth={2.8} color={row.trendColor} />
        </span>
        <span className="font-semibold" style={{ color: row.color === "#E63946" ? row.color : undefined }}>
          {row.status} · {formatValuePct(animatedValue)}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-line2">
        <div className="h-full" style={{ width: `${animatedValue}%`, background: row.color }} />
      </div>
    </div>
  );
}

export function RiskSummaryCard({ rows }: RiskSummaryCardProps) {
  return (
    <Card className="animate-fadeUp p-6">
      <div className="mb-1 flex items-center gap-1.5">
        <h2 className="font-display m-0 text-[17px] font-semibold">Risk Durumu Özeti</h2>
        <InfoTooltip text="Portföyünüzün genel risk profilini dört göstergeyle özetler: Volatilite (değer dalgalanmasının şiddeti), Sektör yoğunlaşması (tek bir sektöre ne kadar bağımlı olduğunuz), Likidite (varlıkları hızlıca nakde çevirebilme gücünüz) ve Kur açıklığı (döviz kuru hareketlerine duyarlılığınız). Her biri kendi hedef bandına göre değerlendirilir — tek bir varlığı değil, portföyün tamamını anlatır." />
      </div>
      <p className="m-0 mb-[18px] text-[13px] text-ink-faint">Hedef bant ile karşılaştırma</p>
      <div className="flex flex-col gap-4">
        {rows.map((row, i) => (
          <RiskSummaryRowItem key={row.id} row={row} index={i} />
        ))}
      </div>
    </Card>
  );
}
