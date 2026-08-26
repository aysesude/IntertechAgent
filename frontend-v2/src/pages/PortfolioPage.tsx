import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/common/Button";
import { Card } from "@/components/common/Card";
import { AssetClassCards } from "@/components/portfolio/AssetClassCards";
import { HoldingsTable } from "@/components/portfolio/HoldingsTable";
import { AssetComparisonChart } from "@/components/portfolio/AssetComparisonChart";
import { usePortfolioData } from "@/hooks/usePortfolioData";

export function PortfolioPage() {
  const { data } = usePortfolioData();

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Varlıklar"
        title="Portföy"
        description={`${data.instrumentCount} enstrüman, ${data.assetClassCount} varlık sınıfı.`}
        actions={<Button>Yeni Pozisyon Ekle</Button>}
      />

      <AssetClassCards assetClasses={data.assetClasses} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2.1fr_1fr]">
        <div>
          <HoldingsTable holdings={data.holdings} />
        </div>
        <div className="flex flex-col gap-4">
          <Card className="p-6">
            <AssetComparisonChart />
          </Card>
        </div>
      </div>
      </div>
    </div>
  );
}
