import { PageHeading } from "@/components/common/PageHeading";
import { MarketTicker } from "@/components/market/MarketTicker";
import { NewsFeed } from "@/components/market/NewsFeed";
import { InfluenceList } from "@/components/market/InfluenceList";
import { CalendarCard } from "@/components/market/CalendarCard";
import { useMarketData } from "@/hooks/useMarketData";

const FILTERS = ["Tümü", "Portföyümü etkileyen", "Makro", "Emtia"];

export function MarketPage() {
  const { data } = useMarketData();

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Piyasa"
        title="Haber Akışı"
        description="Kaynaklardan derlenen içerikler RAG ile özetlenir; her özet kaynağına bağlıdır."
        actions={
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f, i) => (
              <span
                key={f}
                className={
                  "rounded-full px-[15px] py-[9px] text-[12.5px] font-semibold " +
                  (i === 0
                    ? "bg-brand text-white"
                    : i === 1
                      ? "border-[1.5px] border-brand-border text-brand"
                      : "border border-line text-ink-muted")
                }
              >
                {f}
              </span>
            ))}
          </div>
        }
      />

      <MarketTicker indicators={data.indicators} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.9fr_1fr]">
        <NewsFeed news={data.news} />
        <div className="flex flex-col gap-4">
          <InfluenceList rows={data.influence} />
          <CalendarCard events={data.calendar} />
        </div>
      </div>
      </div>
    </div>
  );
}
