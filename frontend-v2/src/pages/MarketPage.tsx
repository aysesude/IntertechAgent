import { PageHeading } from "@/components/common/PageHeading";
import { MarketTicker } from "@/components/market/MarketTicker";
import { NewsFeed } from "@/components/market/NewsFeed";
import { InfluenceList } from "@/components/market/InfluenceList";
import { CalendarCard } from "@/components/market/CalendarCard";
import { useMarketData } from "@/hooks/useMarketData";

// "Tümü" bilerek SONDA: en sağda durması isteniyor, iki temada da.
const FILTERS = ["Portföyümü etkileyen", "Makro", "Emtia", "Tümü"];

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
            {FILTERS.map((f) => (
              <span
                key={f}
                className={
                  "rounded-full px-[15px] py-[9px] text-[12.5px] font-semibold " +
                  (f === "Tümü"
                    ? "bg-brand text-white"
                    : f === "Portföyümü etkileyen"
                      ? // Şeffaf zemin, sayfanın üst bandındaki tabloya karşı
                        // koyu temada neredeyse görünmüyordu — ChatPage'deki
                        // önerilen-soru pilleriyle aynı opak zemin çözümü.
                        "border-[1.5px] border-brand-border bg-white text-brand dark:bg-surface-elevated"
                      : "border border-line bg-white text-ink-muted dark:bg-surface-elevated")
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
