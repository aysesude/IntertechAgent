import { useEffect, useState } from "react";
import type { ApiInsightCard, InsightCardId } from "@/api/insight";

/**
 * Akordeon kartlar: biri geniş ve okunur, diğerleri dar ve dikey başlıklı.
 *
 * TIKLAMAYLA AÇILIR, HOVER İLE DEĞİL. Hover ile açmak, fare kartlara doğru
 * giderken içeriği değiştirir: kullanıcı okumak istediği karta ulaşmadan
 * yanlış kartları açar. Dokunmatikte hover zaten yok. Kayıtlı demo
 * videolarında ise izleyici imleci göremediği için kartlar kendiliğinden
 * açılıp kapanıyormuş gibi görünürdü. Hover yalnızca vurgular.
 */

interface InsightCardsProps {
  cards: ApiInsightCard[];
  /** Açılışta genişleyecek kart — bulunulan sayfanın karşılığı. */
  initialCardId: InsightCardId;
}

export function InsightCards({ cards, initialCardId }: InsightCardsProps) {
  const [acikId, setAcikId] = useState<InsightCardId>(initialCardId);

  // Panel yeniden açıldığında (ya da sayfa değiştiğinde) açık kart, o anki
  // sayfanın kartına döner: kullanıcı Risk sayfasından açtıysa risk kartını
  // görmeli.
  useEffect(() => setAcikId(initialCardId), [initialCardId, cards]);

  return (
    <div className="flex w-full flex-col gap-3 sm:flex-row sm:gap-4">
      {cards.map((kart) => {
        const acik = kart.id === acikId;
        return (
          <button
            key={kart.id}
            onClick={() => setAcikId(kart.id)}
            aria-expanded={acik}
            className={
              "group relative flex overflow-hidden rounded-2xl border border-white/15 bg-white/80 p-5 text-left backdrop-blur-xl transition-all duration-300 " +
              "hover:border-brand/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand " +
              "dark:bg-[#0B151E]/80 " +
              (acik
                ? "flex-col sm:flex-[4]"
                : "flex-row items-center gap-3 sm:flex-[1] sm:flex-col sm:items-start")
            }
          >
            <span
              className={
                "font-display shrink-0 font-semibold text-ink " +
                // Dar haldeyken başlık dikey: dar bir sütunda yatay başlık
                // ya kırpılır ya da kartı gereksiz genişletir.
                (acik
                  ? "text-[17px]"
                  : "text-[15px] sm:[writing-mode:vertical-rl] sm:rotate-180")
              }
            >
              {kart.title}
            </span>

            {acik && (
              <>
                <p className="m-0 mt-3 whitespace-pre-line text-[13.5px] leading-relaxed text-ink-muted">
                  {kart.body}
                </p>
                {kart.degraded && (
                  // Sessizce ham satır göstermek, kullanıcının cilalı bir
                  // cümle beklerken sebebini anlamamasına yol açar.
                  <p className="m-0 mt-3 text-[11.5px] italic text-ink-faint">
                    Bu kart özetlenemedi; ölçülen değerler olduğu gibi gösteriliyor.
                  </p>
                )}
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
