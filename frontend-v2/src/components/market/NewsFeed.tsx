import type { NewsItem } from "@/types/finance";
import { SparkleIcon } from "@/components/icons";
import { CARD_SURFACE_CLASS } from "@/components/common/Card";
import { DANGER, INK_FAINT, INK_SOFT } from "@/utils/colors";

interface NewsFeedProps {
  news: NewsItem[];
}

const IMPACT_COLOR: Record<NonNullable<NewsItem["impact"]>, string> = {
  Yüksek: DANGER,
  Orta: INK_SOFT,
  Düşük: INK_SOFT,
};

export function NewsFeed({ news }: NewsFeedProps) {
  return (
    <div className="flex flex-col gap-3.5">
      {news.map((item) => (
        <article
          key={item.id}
          className={`${CARD_SURFACE_CLASS} p-[22px]`}
        >
          <div className="mb-3 flex flex-wrap items-center gap-2.5">
            {/* Etiket yalnızca GERÇEKTEN varsa çizilir. Canlı akışta konu
                sınıflandırması yok; boş bir rozet uydurulmuş bir kategori
                izlenimi verirdi. */}
            {item.tag && (
              <span
                className={
                  "rounded-md px-[9px] py-1 text-[11px] font-bold uppercase tracking-[.6px] " +
                  (item.isPortfolioRelevant ? "border border-brand-border bg-brand-tint text-brand dark:border-transparent" : "bg-line2 text-ink-muted")
                }
              >
                {item.tag}
              </span>
            )}
            <span className="text-xs text-ink-faint">{item.source}</span>
            <span className="text-xs" style={{ color: INK_FAINT }}>·</span>
            <span className="text-xs text-ink-faint">{item.time}</span>
          </div>
          <h3 className="font-display m-0 mb-2.5 text-[19px] font-semibold leading-[1.35] tracking-[-0.3px]">
            {item.title}
          </h3>
          {/* AI özeti YALNIZCA gerçekten üretilmişse gösterilir. Canlı
              akışta başlık dışında metin yok; özet ürettirmek uydurma
              olurdu, boş bir "AI Özet" kutusu ise ekranı bozardı. */}
          {item.aiSummary && (
            <div className="mb-3.5 border-l-2 border-brand pl-3.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-brand">
                <SparkleIcon size={13} />
                <span className="text-[11px] font-bold uppercase tracking-[.7px]">AI Özet</span>
              </div>
              <p className="m-0 text-[13.5px] leading-[1.65] text-ink-muted">{item.aiSummary}</p>
            </div>
          )}
          <div className="flex items-center gap-3.5 text-xs text-ink-faint">
            <span>
              Etki:{" "}
              <span
                className="font-semibold"
                style={{ color: item.impact ? IMPACT_COLOR[item.impact] : undefined }}
              >
                {item.impact ?? "—"}
              </span>
            </span>
            <span>{item.sourceCount === null ? "—" : `${item.sourceCount} kaynak`}</span>
          </div>
        </article>
      ))}
    </div>
  );
}
