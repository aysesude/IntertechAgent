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
 * geçişliydi. Genişlik artık KAPSAYICININ `grid-template-columns` değeri:
 * tek bir özellik, tek bir geçiş, içerik genişliğinden bağımsız.
 *
 * YÜKSEKLİK GEÇİŞTE SABİT — sıçramanın asıl sebebi buydu. Kartlar geçiş
 * sırasında "birden büyüyüp sonra küçülüyordu" (sahada ölçüldü,
 * 2 Eylül 2026). Sebep akordeonun kendisi değil, METNİN YENİDEN
 * SARMASIYDI: daralan kartın metni daha çok satıra bölünüp UZUYOR,
 * genişleyenin metni kısalıyor; grid satırının yüksekliği en uzun karta göre
 * belirlendiği için satır önce şişip sonra oturuyordu. Yükseklik animasyonu
 * yavaşlatılarak düzelmez — kaynağı genişlik geçişinin kendisidir.
 *
 * Çözüm: geniş ekranda kartlara SABİT yükseklik verildi (`index.css`,
 * `.insight-kartlar`) ve taşan metin kartın içinde kayıyor. Böylece geçiş
 * boyunca yüksekliğin animasyonlanacak bir değeri kalmıyor; yalnızca
 * genişlik değişiyor. Dar ekranda kartlar alt alta olduğu için genişlik hiç
 * değişmez, dolayısıyla sıçrama da yoktur; orada klasik `max-height`
 * akordeonu korunuyor.
 *
 * BAŞLIK İKİ AYRI ELEMAN, DÖNEN TEK ELEMAN DEĞİL. Önce tek bir `<span>`
 * vardı, daralınca `rotate-180` + `writing-mode` alıyordu ve `transition-all`
 * bunu animasyonlayınca başlık kart geçişlerinde kendi ekseninde dönüyordu.
 * Artık dik ve yatay başlık iki ayrı elemandır; aralarında yalnızca çapraz
 * sönümleme olur, hiçbir şey dönerek hareket etmez. Dik başlığın 90°'lik
 * duruşu `writing-mode: vertical-rl` ile SABİTTİR — bir animasyon değil,
 * yazının yönü.
 */

interface InsightCardsProps {
  cards: ApiInsightCard[];
  /** Açılışta genişleyecek kart — bulunulan sayfanın karşılığı. */
  initialCardId: InsightCardId;
}

/**
 * Kartların sırayla belirmesi. Dördü birden aynı anda görünürse panel
 * "yapıştırılmış" gibi açılıyor; küçük bir kayma gözü soldan sağa götürüyor.
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
              "group relative flex min-w-0 flex-col overflow-hidden rounded-2xl border p-5 text-left " +
              "transition-colors duration-500 sm:h-full " +
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand " +
              (acik
                ? "border-brand/30 bg-white/70 dark:bg-white/[0.07]"
                : "border-line/60 bg-white/40 hover:border-brand/40 dark:border-white/10 dark:bg-white/[0.03]")
            }
          >
            {/* DAR HÂL — 90° çevrilmiş başlık, kartın ortasında.
                KONUMU MUTLAK: yerleşime katılmıyor, dolayısıyla belirip
                kaybolurken kartın yüksekliğini oynatmıyor. Yalnızca geniş
                ekranda var; dar ekranda kartlar alt alta olduğu için yatay
                başlık zaten görünür kalır. */}
            <span
              // Görsel bir kopya: erişilebilirlik ağacında BAŞLIK aşağıdaki
              // <h3>'tür, bu span her hâlde okunmaz — yoksa ekran okuyucu her
              // kartın adını iki kez söylerdi.
              aria-hidden
              className={
                "font-display pointer-events-none absolute inset-0 hidden place-items-center " +
                "text-[14px] font-semibold tracking-[0.06em] text-ink [writing-mode:vertical-rl] " +
                "transition-opacity duration-300 sm:grid " +
                (acik ? "opacity-0" : "opacity-100 delay-200")
              }
            >
              {kart.title}
            </span>

            {/* YATAY BAŞLIK. Dar ekranda HER ZAMAN görünür (orada dik başlık
                yok); geniş ekranda kart açıkken belirir. Kapalıyken yerinde
                durup yalnızca sönüyor — kart sabit yükseklikte olduğu için
                görünmez bir satır kaplaması yerleşimi etkilemiyor. */}
            <h3
              className={
                "font-display m-0 shrink-0 text-[17px] font-semibold text-ink " +
                "transition-opacity duration-300 " +
                (acik ? "opacity-100 sm:delay-200" : "opacity-100 sm:opacity-0")
              }
            >
              {kart.title}
            </h3>

            {/* GÖVDE — HER ZAMAN mount: kapanırken DOM'dan çıkmıyor, yalnızca
                sönüyor. Böylece geçiş sırasında yeniden akış tetiklenmiyor.
                Geniş ekranda yükseklik kısıtı YOK (kart zaten sabit yükseklikte
                ve taşan metin içeride kayıyor); dar ekranda `max-height`
                akordeonu devrede. */}
            <div
              aria-hidden={!acik}
              className={
                "flex min-h-0 flex-1 flex-col overflow-hidden transition-opacity duration-300 " +
                (acik
                  ? "max-h-none opacity-100 delay-200"
                  : "max-h-0 opacity-0 sm:max-h-none")
              }
            >
              <div className="min-h-0 flex-1 overflow-y-auto">
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
            </div>
          </motion.button>
        );
      })}
    </div>
  );
}
