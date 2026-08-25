import type { StrategyRecommendation } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { SparkleIcon } from "@/components/icons";

interface StrategyRecommendationsProps {
  recommendations: StrategyRecommendation[];
}

const PRIORITY_STYLES: Record<StrategyRecommendation["priority"], string> = {
  Öncelikli: "text-danger bg-danger-tint",
  "Orta vadeli": "text-brand bg-brand-tint",
  İzleme: "text-ink-muted bg-line2",
};

export function StrategyRecommendations({ recommendations }: StrategyRecommendationsProps) {
  return (
    <Card className="p-6">
      <div className="mb-[18px] flex items-center gap-2.5">
        <span className="text-brand">
          <SparkleIcon size={18} />
        </span>
        <h2 className="font-display m-0 text-[17px] font-semibold">Kişiselleştirilmiş Strateji Önerileri</h2>
      </div>
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {recommendations.map((rec) => (
          <div
            key={rec.id}
            className="rounded-[10px] border border-line p-5 transition-shadow hover:border-brand hover:shadow-card"
          >
            <div className={`mb-3 inline-block rounded-md px-[9px] py-[5px] text-[11px] font-bold uppercase tracking-[.6px] ${PRIORITY_STYLES[rec.priority]}`}>
              {rec.priority}
            </div>
            <h3 className="m-0 mb-2 text-[15.5px] font-semibold">{rec.title}</h3>
            <p className="m-0 mb-3.5 text-[13.5px] leading-[1.6] text-ink-muted">{rec.description}</p>
            <div className="text-[12.5px] text-ink-faint">{rec.expectedImpact}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
