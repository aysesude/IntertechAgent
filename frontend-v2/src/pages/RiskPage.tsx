import { PageHeading } from "@/components/common/PageHeading";
import { RiskGauge } from "@/components/risk/RiskGauge";
import { RiskFactorsList } from "@/components/risk/RiskFactorsList";
import { RiskMetricsRow } from "@/components/risk/RiskMetricsRow";
import { StrategyRecommendations } from "@/components/risk/StrategyRecommendations";
import { useRiskData } from "@/hooks/useRiskData";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";

export function RiskPage() {
  const { data } = useRiskData();

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Profil"
        title="Risk Analizi"
        description="Skor; volatilite, yoğunlaşma, kur açıklığı ve yatırım ufkundan hesaplanır. Son değerlendirme 03 Ağustos."
      />

      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1.35fr]">
        <RiskGauge score={data.profile.score} label={data.profile.label} description={data.profile.description} />
        <RiskFactorsList factors={data.factors} />
      </div>

      <RiskMetricsRow valueAtRisk={data.valueAtRisk} sharpeRatio={data.sharpeRatio} limitedHistoryWarning={data.limitedHistoryWarning} />

      <StrategyRecommendations recommendations={data.recommendations} />

      <p className="m-0 mt-4 text-center text-xs italic text-ink-soft dark:text-ink-faint">{INVESTMENT_DISCLAIMER}</p>
      </div>
    </div>
  );
}
