import { useState } from "react";
import { Card } from "@/components/common/Card";
import type { Insight, InsightAgent, InsightSeverity } from "@/types/insight";
import { formatSignedTRY } from "@/utils/format";

const SEVERITY_STRIPE: Record<InsightSeverity, string> = {
  uyari: "bg-danger",
  olumlu: "bg-brand",
  bilgi: "bg-ink-faint",
};

const AGENT_LABEL: Record<InsightAgent, string> = {
  portfoy: "Portföy Ajanı",
  risk: "Risk Ajanı",
  piyasa: "Piyasa Ajanı",
};

interface InsightCardProps {
  insight: Insight;
}

export function InsightCard({ insight }: InsightCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="relative overflow-hidden pl-7">
      <span className={`absolute inset-y-0 left-0 w-1 ${SEVERITY_STRIPE[insight.severity]}`} />

      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display m-0 text-[15px] font-semibold">{insight.title}</h3>
        <span className="shrink-0 whitespace-nowrap rounded-full border border-line px-2 py-0.5 text-[10.5px] font-medium text-ink-muted">
          {AGENT_LABEL[insight.agent]}
        </span>
      </div>

      <p className="m-0 mt-1.5 text-[13.5px] leading-relaxed text-ink-muted">{insight.body}</p>

      {insight.amountTRY != null && (
        <div className={`mt-2 text-[13.5px] font-semibold ${insight.amountTRY >= 0 ? "text-brand" : "text-danger"}`}>
          {formatSignedTRY(insight.amountTRY)}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-2.5 text-[12.5px] font-semibold text-ink-faint transition-colors hover:text-brand"
      >
        {open ? "Neden? ▴" : "Neden? ▾"}
      </button>

      {open && (
        <div className="animate-fadeUp mt-2 flex flex-col gap-1.5 border-t border-line2 pt-2.5">
          {insight.evidence.map((item, i) => (
            <div key={i} className="flex items-center justify-between gap-3 text-[12.5px]">
              <span className="text-ink-faint">{item.label}</span>
              <span className="font-semibold text-ink-soft">{item.value}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
