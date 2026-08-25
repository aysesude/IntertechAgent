import type { AIRecommendation } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { SparkleIcon } from "@/components/icons";

interface AIRecommendationsListProps {
  recommendations: AIRecommendation[];
}

export function AIRecommendationsList({ recommendations }: AIRecommendationsListProps) {
  return (
    <Card className="p-6">
      <div className="mb-4 flex items-center gap-2.5">
        <span className="text-brand">
          <SparkleIcon size={18} />
        </span>
        <h2 className="font-display m-0 text-[17px] font-semibold">AI Önerileri</h2>
        <span className="ml-auto rounded-md border border-brand-border px-2 py-1 text-[11px] font-semibold text-brand">
          {recommendations.length} yeni
        </span>
      </div>
      <div className="flex flex-col gap-3">
        {recommendations.map((rec) => (
          <div
            key={rec.id}
            className="rounded-[10px] border border-line p-[15px] transition-colors hover:border-brand hover:bg-[#FCFDFF] dark:hover:bg-white/5"
          >
            <div className="mb-1.5 text-sm font-semibold">{rec.title}</div>
            <p className="m-0 text-[13px] leading-[1.55] text-ink-muted">{rec.description}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}
