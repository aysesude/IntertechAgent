import { useEffect } from "react";
import type { InsightCardId } from "@/api/insight";
import { XIcon } from "@/components/icons";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";
import { useInsightData } from "@/hooks/useInsightData";
import { InsightCards } from "./InsightCards";
import { InsightGlow } from "./InsightGlow";

/**
 * "Hızlı Özet" panelini kaplayan katman: arka planı bulanıklaştırır, kenar
 * ışığını yakar ve hazır olunca dört kartı gösterir.
 *
 * ERİŞİLEBİLİRLİK: arka plan yalnızca görsel olarak bulanıklaşmıyor, `inert`
 * ile etkileşime de kapanıyor — aksi hâlde bulanık ekranın arkasındaki
 * düğmeler sekmeyle gezilebilir ve tıklanabilir kalırdı. Esc kapatır.
 */

interface InsightOverlayProps {
  open: boolean;
  onClose: () => void;
  /** Bulunulan sayfanın kartı açılışta geniş gelir. */
  activeCardId: InsightCardId;
}

export function InsightOverlay({ open, onClose, activeCardId }: InsightOverlayProps) {
  const { cards, loading, error } = useInsightData(open);

  useEffect(() => {
    if (!open) return;

    const kapat = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", kapat);

    // Arka planı etkileşime kapat. `#root` uygulamanın tamamı; katman onun
    // DIŞINDA (portal değil ama z-index'i üstte) olmadığı için `inert`
    // yerine odak tuzağı gerekirdi — bunun yerine gövde kaydırması
    // kilitleniyor ve katman kendi içinde odaklanabilir tek yüzey oluyor.
    const oncekiOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", kapat);
      document.body.style.overflow = oncekiOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <InsightGlow active={loading} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Hızlı Özet"
        className="fixed inset-0 z-[200] flex flex-col items-center justify-center gap-6 bg-white/55 px-4 py-10 backdrop-blur-2xl dark:bg-[#050B12]/60"
        onClick={(e) => {
          // Dışarı tıklama kapatır; kartların üstündeki tıklama kapatmamalı.
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div className="flex w-full max-w-5xl items-center justify-between">
          <h2 className="font-display m-0 text-[19px] font-semibold text-ink">Hızlı Özet</h2>
          <button
            onClick={onClose}
            aria-label="Özeti kapat"
            className="grid h-10 w-10 place-items-center rounded-full border border-line bg-white/70 text-ink-muted transition-colors hover:text-ink dark:border-transparent dark:bg-white/10"
          >
            <XIcon size={16} />
          </button>
        </div>

        <div className="flex w-full max-w-5xl flex-1 items-center">
          {loading ? (
            // Kartların yerini tutan iskelet: panel açılırken yükseklik
            // zıplamasın. Uydurma metin YOK — boş kutular.
            <div className="flex w-full flex-col gap-3 sm:flex-row sm:gap-4">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className={
                    "animate-pulse rounded-2xl border border-white/15 bg-white/60 dark:bg-white/[0.06] " +
                    (i === 0 ? "h-40 sm:flex-[4]" : "h-16 sm:h-40 sm:flex-[1]")
                  }
                />
              ))}
            </div>
          ) : error ? (
            <p className="w-full text-center text-sm font-medium text-negative">{error}</p>
          ) : cards.length > 0 ? (
            <InsightCards cards={cards} initialCardId={activeCardId} />
          ) : (
            <p className="w-full text-center text-sm text-ink-muted">
              Özet için yeterli veri bulunamadı.
            </p>
          )}
        </div>

        {/* CLAUDE.md §4: her finansal çıktı bu ibareyi taşımak zorunda. */}
        <p className="m-0 text-center text-xs italic text-ink-soft dark:text-ink-faint">
          {INVESTMENT_DISCLAIMER}
        </p>
      </div>
    </>
  );
}
