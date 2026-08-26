import { Card } from "@/components/common/Card";
import type { PeriodReturn, ReturnPeriodKey } from "@/types/finance";
import { formatPct } from "@/utils/format";
import { BRAND } from "@/utils/colors";

const PERIOD_ORDER: ReturnPeriodKey[] = ["gunluk", "haftalik", "aylik"];
const PERIOD_LABELS: Record<ReturnPeriodKey, string> = {
  gunluk: "Gün",
  haftalik: "Hafta",
  aylik: "Ay",
};

interface PeriodReturnCardProps {
  // Backend veriyi henüz sağlamıyor olabilir ya da hesaplama başarısız
  // olabilir — bu yüzden hem tüm kayıt hem de tekil dönem opsiyonel kabul
  // edilir; her iki durumda da "veri yok" fallback'i gösterilir (AK-1.3/1.6).
  periodReturns?: Partial<Record<ReturnPeriodKey, PeriodReturn>>;
  active: ReturnPeriodKey;
  onChange: (period: ReturnPeriodKey) => void;
}

export function PeriodReturnCard({ periodReturns, active, onChange }: PeriodReturnCardProps) {
  const current = periodReturns?.[active];

  return (
    <Card className="p-[22px]">
      <div className="mb-3.5 flex min-h-[28px] items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-[.4px] text-ink-faint">Getiri</span>
        <div className="flex gap-1 rounded-[8px] border border-line p-[2px] dark:border-transparent dark:bg-white/5">
          {PERIOD_ORDER.map((key) => (
            <button
              key={key}
              onClick={() => onChange(key)}
              className={
                "rounded-[6px] px-2 py-1 text-[10.5px] font-semibold transition-colors " +
                (key === active ? "bg-brand text-white" : "bg-transparent text-ink-muted hover:text-ink")
              }
            >
              {PERIOD_LABELS[key]}
            </button>
          ))}
        </div>
      </div>
      {current ? (
        <>
          <div className="font-display text-[31px] font-bold tracking-[-0.8px]" style={{ color: BRAND }}>
            {formatPct(current.returnPct)}
          </div>
          <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold">
            <span className="font-medium text-ink-faint">BIST 100: {formatPct(current.benchmarkPct)}</span>
          </div>
        </>
      ) : (
        <>
          <div className="font-display text-[31px] font-bold tracking-[-0.8px] text-ink-faint">—</div>
          <div className="mt-2.5 text-sm font-medium text-ink-faint">Bu dönem için veri yok</div>
        </>
      )}
    </Card>
  );
}
