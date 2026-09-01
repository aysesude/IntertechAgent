import { useEffect, useState } from "react";
import type { ApiInsightCard, InsightCardId } from "@/api/insight";

/**
 * Akordeon kartlar: biri geniş ve okunur, diğerleri dar ve dikey başlıklı.
 *
 * TIKLAMAYLA AÇILIR, HOVER İLE DEĞİL. Hover ile açmak, fare kartlara doğru
 * giderken içeriği değiştirir: kullanıcı okumak istediği karta ulaşmadan
 * yanlış kartları açar. Dokunmatikte hover zaten yok. Kayıtlı demo
 * videolarında ise izleyici imleci göremediği için kartlar kendiliğinden
 * açılıp kapanıyormuş gibi görünürdü.
 *
 * GEÇİŞ NEDEN GRID ÜZERİNDEN. Önce flex-basis (`flex-[4]` ↔ `flex-[1]`)
 * geçişliydi ve kartlar "birden büyüyüp birden küçülüp sonra genişliyordu"
 * (sahada ölçüldü, 2 Eylül 2026). İki sebep vardı: (1) gövde metni açılıp
 * kapanırken mount/unmount oluyor, her seferinde yeniden akış tetikliyordu;
 * (2) flex-basis geçişi, içerik genişliğiyle yarışıyordu.
 *
 * Çözüm ikisini de kaldırıyor: genişlik artık KAPSAYICININ
 * `grid-template-columns` değeri (tek bir özellik, tek bir geçiş) ve gövde
 * metni HER ZAMAN mount — yalnızca opaklığı ve görünürlüğü değişiyor.
 * Dolayısıyla açılıp kapanırken DOM'a hiçbir şey girip çıkmıyor.
 */

interface InsightCardsProps {
  cards: ApiInsightCard[];
  /** Açılışta genişleyecek kart — bulunulan sayfanın karşılığı. */
  initialCardId: InsightCardId;
}

export function InsightCards({ cards, initialCardId }: InsightCardsProps) {
  const [acikId, setAcikId] = useState<InsightCardId>(initialCardId);

  // Panel yeniden açıldığında (ya da sayfa değiştiğinde) açık kart, o anki
  // sayfanın kartına döner.
  useEffect(() => setAcikId(initialCardId), [initialCardId, cards]);

  const sutunlar = cards.map((k) => (k.id === acikId ? "5fr" : "1fr")).join(" ");

  return (
    <div
      className="insight-kartlar"
      // Geçişin tek konusu bu değer; `index.css` onu animasyonluyor.
      style={{ ["--insight-sutunlar" as string]: sutunlar } as React.CSSProperties}
    >
      {cards.map((kart) => {
        const acik = kart.id === acikId;
        return (
          <button
            key={kart.id}
            onClick={() => setAcikId(kart.id)}
            aria-expanded={acik}
            className={
              "group relative flex min-w-0 overflow-hidden rounded-2xl border p-5 text-left transition-colors duration-300 " +
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand " +
              (acik
                ? "flex-col border-brand/30 bg-white/70 dark:bg-white/[0.07]"
                : "flex-row items-center gap-3 border-line/60 bg-white/40 hover:border-brand/40 dark:border-white/10 dark:bg-white/[0.03] sm:flex-col sm:items-start")
            }
          >
            <span
              className={
                "font-display shrink-0 font-semibold text-ink transition-all duration-300 " +
                (acik ? "text-[17px]" : "text-[15px] sm:[writing-mode:vertical-rl] sm:rotate-180")
              }
            >
              {kart.title}
            </span>

            {/* Gövde HER ZAMAN mount: kapanırken DOM'dan çıkmıyor, yalnızca
                opaklığı ve yüksekliği sıfırlanıyor. Böylece geçiş sırasında
                yeniden akış (reflow) tetiklenmiyor. */}
            <div
              aria-hidden={!acik}
              className={
                "min-w-0 overflow-hidden transition-all duration-300 " +
                (acik ? "mt-3 max-h-[46vh] opacity-100" : "max-h-0 opacity-0")
              }
            >
              <p className="m-0 whitespace-pre-line text-[13.5px] leading-relaxed text-ink-muted">
                {kart.body}
              </p>
              {kart.degraded && (
                // Sessizce ham satır göstermek, kullanıcının cilalı bir cümle
                // beklerken sebebini anlamamasına yol açar.
                <p className="m-0 mt-3 text-[11.5px] italic text-ink-faint">
                  Bu kart özetlenemedi; ölçülen değerler olduğu gibi gösteriliyor.
                </p>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
