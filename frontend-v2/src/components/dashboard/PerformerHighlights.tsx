import { TrendingUp, TrendingDown } from "lucide-react";
import { Card } from "@/components/common/Card";
import type { AssetPerformer } from "@/types/finance";
import { formatPct } from "@/utils/format";

interface PerformerHighlightsProps {
  // Backend veriyi henüz sağlamıyor olabilir — bu yüzden opsiyonel; eksikse
  // kart yer kaplamaya devam eder ama "veri yok" gösterir (AK-1.3/1.6).
  best?: AssetPerformer;
  worst?: AssetPerformer;
}

function PerformerTile({ label, performer, positive }: { label: string; performer?: AssetPerformer; positive: boolean }) {
  const Icon = positive ? TrendingUp : TrendingDown;
  const hasData = performer != null;
  return (
    <div className="flex items-center gap-3.5 rounded-[10px] border border-line p-4">
      <span
        className={`grid h-10 w-10 shrink-0 place-items-center rounded-[9px] ${hasData ? (positive ? "bg-brand-tint text-brand dark:bg-[rgba(70,199,154,0.14)] dark:text-[#46C79A]" : "bg-danger-tint text-danger dark:bg-[rgba(255,107,114,0.14)] dark:text-[#FF6B72]") : "bg-line2 text-ink-faint"}`}
      >
        <Icon size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold uppercase tracking-[.4px] text-ink-faint">{label}</div>
        {hasData ? (
          <div className="truncate text-sm font-semibold">
            {performer.name} <span className="font-normal text-ink-faint">· {performer.assetClass}</span>
          </div>
        ) : (
          <div className="text-sm font-medium text-ink-faint">Veri yok</div>
        )}
      </div>
      <div className={`text-[17px] font-bold ${hasData ? (positive ? "text-brand dark:text-[#46C79A]" : "text-danger dark:text-[#FF6B72]") : "text-ink-faint"}`}>
        {hasData ? formatPct(performer.returnPct) : "—"}
      </div>
    </div>
  );
}

export function PerformerHighlights({ best, worst }: PerformerHighlightsProps) {
  return (
    <Card className="mb-6 p-6">
      <h2 className="font-display m-0 mb-4 text-[17px] font-semibold">Performansta Öne Çıkanlar</h2>
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
        <PerformerTile label="En İyi Performans" performer={best} positive />
        <PerformerTile label="En Kötü Performans" performer={worst} positive={false} />
      </div>
    </Card>
  );
}
