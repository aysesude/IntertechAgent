import { useState } from "react";
import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/common/Button";
import { Card } from "@/components/common/Card";
import { AssetClassCards } from "@/components/portfolio/AssetClassCards";
import { HoldingsTable } from "@/components/portfolio/HoldingsTable";
import { TargetVsActualChart } from "@/components/portfolio/TargetVsActualChart";
import { AssetComparisonChart } from "@/components/portfolio/AssetComparisonChart";
import { usePortfolioData } from "@/hooks/usePortfolioData";
import { LineChart as LineChartIcon, LayoutGrid } from "lucide-react";

export function PortfolioPage() {
  const { data } = usePortfolioData();
  const [showComparison, setShowComparison] = useState(false);

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Varlıklar"
        title="Portföy"
        description={`${data.instrumentCount} enstrüman, ${data.assetClassCount} varlık sınıfı. Ağırlıklar hedef bandına göre değerlendirildi.`}
        actions={<Button>Yeni Pozisyon Ekle</Button>}
      />

      <AssetClassCards assetClasses={data.assetClasses} />

      <div className="mb-4 flex justify-end gap-2">
        <button
          onClick={() => setShowComparison((v) => !v)}
          className={
            "flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-[12.5px] font-semibold transition-colors " +
            (showComparison
              ? "border-brand bg-brand-tint text-brand"
              : "border-line text-ink-muted hover:border-brand hover:text-brand")
          }
        >
          {showComparison ? <LayoutGrid size={14} /> : <LineChartIcon size={14} />}
          {showComparison ? "Pozisyonlara Dön" : "Varlıkları Karşılaştır"}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2.1fr_1fr]">
        <div>
          {showComparison ? (
            <Card className="animate-fadeUp p-6">
              <AssetComparisonChart variant="standalone" />
            </Card>
          ) : (
            <HoldingsTable holdings={data.holdings} />
          )}
        </div>
        <div className="flex flex-col gap-4">
          <TargetVsActualChart rows={data.targetVsActual} />
        </div>
      </div>
      </div>
    </div>
  );
}
