import { Card } from "@/components/common/Card";
import { InsightCard } from "@/components/dashboard/InsightCard";
import type { Insight } from "@/types/insight";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";

interface InsightsBandProps {
  insights: Insight[];
}

export function InsightsBand({ insights }: InsightsBandProps) {
  // Bandın kendisi "çalışan ajan sayısı"nı ayrıca bilmiyor — elindeki tek veri
  // insights dizisi, o yüzden bu sayı üretilen içgörülerdeki BENZERSİZ ajan
  // sayısından türetiliyor (örn. hem portföy hem risk ajanı içgörü ürettiyse: 2).
  const agentCount = new Set(insights.map((i) => i.agent)).size;
  const time = new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="mb-6">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display m-0 text-[17px] font-semibold">VİRA'nın notu</h2>
        <span className="whitespace-nowrap text-[12px] text-ink-faint">
          {agentCount} ajan çalıştı · {time}
        </span>
      </div>

      {insights.length === 0 ? (
        <Card className="p-6 text-center text-[13.5px] text-ink-faint">
          Şu an dikkat gerektiren bir durum görünmüyor.
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      )}

      <p className="m-0 mt-3 text-[11px] italic text-ink-faint">{INVESTMENT_DISCLAIMER}</p>
    </div>
  );
}
