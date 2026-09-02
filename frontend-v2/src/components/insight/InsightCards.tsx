import { useEffect, useState } from "react";
import { motion } from "framer-motion";
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
 *
 * BAŞLIK İKİ AYRI ELEMAN, DÖNEN TEK ELEMAN DEĞİL. Önce tek bir `<span>`
 * vardı ve daralınca `rotate-180` + `writing-mode` alıyordu; `transition-all`
 * bunu animasyonlayınca başlık kart geçişlerinde kendi ekseninde dönüyordu
 * (sahada ölçüldü, 2 Eylül 2026). Artık dikey ve yatay başlık iki ayrı
 * elemandır ve aralarında yalnızca ÇAPRAZ SÖNÜMLEME olur — hiçbir şey
 * dönmez. Dikey başlıkta `text-orientation: upright` kullanılıyor: harfler
 * yan yatmadan alt alta dizilir, yani gerçekten "dik", döndürülmüş değil.
 */

interface InsightCardsProps {
  cards: ApiInsightCard[];
  /** Açılışta genişleyecek kart — bulunulan sayfanın karşılığı. */
  initialCardId: InsightCardId;
}

/**
 * Kartların sırayla belirmesi. Dördü birden aynı anda görünürse panel
 * "yapıştırılmış" gibi açılıyor; küçük bir kayma gözü soldan sağa götürüyor.
 * Süre kısa tutuldu (toplam ~0.4 sn): bekleme zaten bitmiş durumda, buradan
 * sonrası okuma zamanı.
 */
const BELIRME_ADIMI_SN = 0.07;

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
      {cards.map((kart, sira) => {
        const acik = kart.id === acikId;
        return (
          <motion.button
            key={kart.id}
            onClick={() => setAcikId(kart.id)}
            aria-expanded={acik}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.34,
              delay: sira * BELIRME_ADIMI_SN,
              ease: [0.22, 1, 0.36, 1],
            }}
            className={
              "group relative flex min-w-0 flex-col overflow-hidden rounded-2xl border p-5 text-left transition-colors duration-300 " +
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand " +
              (acik
                ? "border-brand/30 bg-white/70 dark:bg-white/[0.07]"
                : "items-center border-line/60 bg-white/40 hover:border-brand/40 dark:border-white/10 dark:bg-white/[0.03] sm:items-start")
            }
          >
            {/* DAR HÂL — dik başlık. Döndürülmüyor: `upright` ile harfler
                normal yönde, alt alta. Kapalıyken yer kaplamaması için
                yüksekliği değil OPAKLIĞI ve `max-h`'si sıfırlanıyor; eleman
                DOM'da kalır (yukarıdaki gerekçe). */}
            <span
              aria-hidden={acik}
              className={
                "font-display shrink-0 overflow-hidden font-semibold tracking-[0.08em] text-ink " +
                "transition-opacity duration-200 [text-orientation:upright] [writing-mode:vertical-rl] " +
                (acik ? "max-h-0 opacity-0" : "text-[13px] opacity-100")
              }
            >
              {kart.title}
            </span>

            {/* GENİŞ HÂL — yatay başlık, gövdenin üstünde. */}
            <div
              aria-hidden={!acik}
              className={
                "min-w-0 overflow-hidden transition-all duration-300 " +
                (acik ? "max-h-[52vh] opacity-100" : "max-h-0 opacity-0")
              }
            >
              <h3 className="font-display m-0 text-[17px] font-semibold text-ink">{kart.title}</h3>
              <p className="m-0 mt-3 whitespace-pre-line text-[13.5px] leading-relaxed text-ink-muted">
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
          </motion.button>
        );
      })}
    </div>
  );
}
