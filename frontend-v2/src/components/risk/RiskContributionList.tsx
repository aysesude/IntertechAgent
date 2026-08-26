import { Card } from "@/components/common/Card";
import { formatNumberTR } from "@/utils/format";
import type { RiskCategoryContribution } from "@/types/finance";

interface RiskContributionListProps {
  contributions: RiskCategoryContribution[];
}

/**
 * "Risk nereden geliyor" — her varlık sınıfının toplam portföy VARYANSINA
 * katkısı (`risk_contribution_percent`). Ağırlık (%) ile KARIŞTIRILMAMALI:
 * küçük ama oynak bir sınıf, büyük ama sakin bir sınıftan daha çok risk
 * taşıyabilir (bkz. adapters/risk.ts).
 */
export function RiskContributionList({ contributions }: RiskContributionListProps) {
  const maxContribution = Math.max(...contributions.map((c) => c.riskContributionPct ?? 0), 1);

  return (
    <Card className="p-6">
      <h2 className="font-display m-0 mb-1 text-[17px] font-semibold">Risk Nereden Geliyor</h2>
      <p className="m-0 mb-[18px] text-[13px] text-ink-faint">
        Her varlık sınıfının toplam portföy riskine katkısı
      </p>
      <div className="flex flex-col gap-[15px]">
        {contributions.map((c) => {
          const pct = c.riskContributionPct;
          const widthPct = pct === null ? 0 : (pct / maxContribution) * 100;
          return (
            <div key={c.id}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[13.5px] font-semibold text-ink-soft">{c.name}</span>
                <span className="font-display text-[13.5px] font-bold" style={{ color: c.color }}>
                  {pct === null ? "—" : `%${formatNumberTR(pct, 1)}`}
                </span>
              </div>
              <div className="h-[7px] overflow-hidden rounded-full bg-line2">
                <div className="h-full rounded-full transition-all" style={{ width: `${widthPct}%`, background: c.color }} />
              </div>
              <p className="m-0 mt-1.5 text-[12.5px] text-ink-muted">
                Ağırlık %{formatNumberTR(c.weightPct, 1)} · Yıllık volatilite{" "}
                {c.volatilityPct === null ? "—" : `%${formatNumberTR(c.volatilityPct, 1)}`}
              </p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
