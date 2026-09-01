import { useEffect, useRef, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import type { InsightCardId } from "@/api/insight";
import { XIcon } from "@/components/icons";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";
import { useInsightData } from "@/hooks/useInsightData";
import { InsightCards } from "./InsightCards";
import { InsightGlow } from "./InsightGlow";

/**
 * "Hızlı Özet" katmanı — İKİ AŞAMALI.
 *
 * 1. **Hazırlanıyor:** ekranda YALNIZCA kenar ışığı yanar. Panel yok,
 *    bulanıklık yok, iskelet kart yok. Kullanıcı sayfasını görmeye devam
 *    eder; ışık "arkada bir şey çalışıyor" der.
 * 2. **Hazır:** arka plan bulanıklaşıp hafifçe kararır, sayfanın ortasında
 *    yarım ekranlık bir panel belirir ve kartlar içindedir.
 *
 * NEDEN İKİ AŞAMA. İlk sürüm açılır açılmaz tam ekran bir katman ve BOŞ
 * iskelet kartlar gösteriyordu (sahada ölçüldü, 2 Eylül 2026: "bam diye bir
 * sayfa açıldı ve boş kartlar göründü"). İskelet, gelecek içeriğin şeklini
 * taklit ederek bir vaatte bulunuyordu; içerik gelene kadar da kullanıcı boş
 * bir tam ekranın önünde bekliyordu. Işık aynı bilgiyi (çalışıyor) sayfayı
 * kaçırmadan veriyor.
 *
 * ERİŞİLEBİLİRLİK — panel görünürken iki koruma birden:
 * odak tuzağı (Tab katmanın içinde döner) ve `inert` (arka plan
 * erişilebilirlik ağacından çıkar, ekran okuyucu okumaz). İkisi ayrı
 * şeylerdir, biri diğerinin yerini tutmaz. Hazırlanma aşamasında hiçbiri
 * uygulanmaz: sayfa hâlâ kullanıcınındır.
 *
 * React 18 `inert`'i prop olarak tanımıyor (React 19'da var); öznitelik ref
 * üzerinden veriliyor. Yükseltme GEREKMİYOR — davranış birebir aynı ve React
 * 19'a geçmek recharts/framer-motion/google-charts zincirini de yükseltmek
 * demekti (karar, 2 Eylül 2026).
 *
 * PORTAL: `document.body` altına taşınıyor. `backdrop-filter` kullanan bir
 * ata, içindeki `position: fixed` elemanlar için yeni bir containing block
 * oluşturup katmanı o kutuya hapsedebiliyor (aynı gerekçe
 * `HoldingReturnDetail`'de de yazılı).
 */

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** Uygulama kapsayıcısı (bkz. `index.html`). */
const UYGULAMA_KOKU_ID = "root";

const GECIS = { duration: 0.32, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] };

interface InsightOverlayProps {
  open: boolean;
  onClose: () => void;
  /** Bulunulan sayfanın kartı açılışta geniş gelir. */
  activeCardId: InsightCardId;
}

export function InsightOverlay({ open, onClose, activeCardId }: InsightOverlayProps) {
  const { cards, loading, error, refetch } = useInsightData(open);
  const panelRef = useRef<HTMLDivElement>(null);

  // `onClose` REF'TE, bağımlılık listesinde DEĞİL: çağıran taraf onu satır içi
  // ok fonksiyonu olarak veriyor (her render'da yeni kimlik). Bağımlılıkta
  // kalsaydı ebeveynin her render'ında efekt temizlenip yeniden kurulur,
  // `inert` gidip gelir ve odak paneli açan düğmeye sıçrardı.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Panel yalnızca hazırlık BİTTİĞİNDE görünür.
  const panelGorunur = open && !loading;

  // Esc her iki aşamada da kapatır: hazırlanırken de vazgeçilebilmeli.
  useEffect(() => {
    if (!open) return;
    const kapat = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", kapat);
    return () => document.removeEventListener("keydown", kapat);
  }, [open]);

  // Kilitler YALNIZCA panel görünürken: hazırlanma aşamasında sayfa hâlâ
  // kullanıcının.
  useEffect(() => {
    if (!panelGorunur) return;

    const oncekiOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const kok = document.getElementById(UYGULAMA_KOKU_ID);
    kok?.setAttribute("inert", "");

    const oncekiOdak = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    return () => {
      document.body.style.overflow = oncekiOverflow;
      kok?.removeAttribute("inert");
      // `inert` kalkmadan odak verilemez: inert bir ağaçtaki öğe odak almaz.
      oncekiOdak?.focus?.();
    };
  }, [panelGorunur]);

  /** Tab tuzağı — `HoldingReturnDetail`'deki kalıbın aynısı. */
  function odagiTut(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const kok = panelRef.current;
    if (!kok) return;
    const odaklanabilir = kok.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    if (odaklanabilir.length === 0) return;
    const ilk = odaklanabilir[0];
    const son = odaklanabilir[odaklanabilir.length - 1];
    if (e.shiftKey && document.activeElement === ilk) {
      e.preventDefault();
      son.focus();
    } else if (!e.shiftKey && document.activeElement === son) {
      e.preventDefault();
      ilk.focus();
    }
  }

  if (!open) return null;

  return createPortal(
    <>
      <InsightGlow active={loading} />

      <AnimatePresence>
        {panelGorunur && (
          <>
            <motion.div
              key="perde"
              aria-hidden
              onClick={onClose}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={GECIS}
              // Bulanık + HAFİF karartılmış: yalnızca bulanıklık, açık temada
              // paneli zeminden ayırmaya yetmiyordu.
              className="fixed inset-0 z-[195] bg-[#0B0E14]/25 backdrop-blur-xl dark:bg-black/45"
            />

            <motion.div
              key="panel"
              ref={panelRef}
              role="dialog"
              aria-modal="true"
              aria-label="Hızlı Özet"
              tabIndex={-1}
              onKeyDown={odagiTut}
              initial={{ opacity: 0, y: 18, scale: 0.985 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.99 }}
              transition={GECIS}
              // YARIM SAYFA: tam ekran değil. Kartlar ekranın ortasında bir
              // yüzey üzerinde durur, arkasındaki sayfa görünmeye devam eder.
              //
              // `max-h` ZORUNLU: panel dikeyde ortalanmış (`-translate-y-1/2`)
              // ve yükseklik sınırı olmayınca uzun içerik ekranın ALTINDAN VE
              // ÜSTÜNDEN birden taşıyordu — üst kısım hiç ulaşılamaz hâle
              // geliyordu (sahada ölçüldü, 2 Eylül 2026). Sınır + iç kaydırma
              // (aşağıdaki `min-h-0 overflow-y-auto`) ikisi birlikte gerekli:
              // yalnızca `max-h` içeriği kırpar, yalnızca kaydırma taşmayı
              // durdurmaz.
              className="fixed left-1/2 top-1/2 z-[200] flex max-h-[88vh] w-[min(1100px,92vw)] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-3xl border border-white/20 bg-white/85 p-6 shadow-pop outline-none backdrop-blur-2xl dark:border-white/10 dark:bg-[#0B151E]/85 sm:p-7"
            >
              <div className="flex items-center justify-between">
                <h2 className="font-display m-0 text-[19px] font-semibold text-ink">Hızlı Özet</h2>
                <button
                  onClick={onClose}
                  aria-label="Özeti kapat"
                  className="grid h-10 w-10 place-items-center rounded-full border border-line bg-white/70 text-ink-muted transition-colors hover:text-ink dark:border-transparent dark:bg-white/10"
                >
                  <XIcon size={16} />
                </button>
              </div>

              {/* KAYDIRILABİLİR ORTA BÖLGE. Başlık ve sorumluluk reddi sabit
                  kalır, yalnızca kartlar kayar — uyarı, kaydırılıp gözden
                  kaybolabilen bir yerde durmamalı (CLAUDE.md §4). `min-h-0`
                  olmadan flex çocuğu küçülmez ve kaydırma hiç çalışmaz. */}
              <div className="min-h-0 flex-1 overflow-y-auto">
              {error ? (
                <div className="flex flex-col items-center gap-3 py-8">
                  <p className="m-0 text-center text-sm font-medium text-negative">{error}</p>
                  <button
                    onClick={refetch}
                    className="rounded-full border border-line px-4 py-2 text-[13px] font-semibold text-ink transition-colors hover:border-brand/50 dark:border-transparent dark:bg-white/10"
                  >
                    Tekrar dene
                  </button>
                </div>
              ) : cards.length > 0 ? (
                <InsightCards cards={cards} initialCardId={activeCardId} />
              ) : (
                <p className="py-8 text-center text-sm text-ink-muted">
                  Özet için yeterli veri bulunamadı.
                </p>
              )}
              </div>

              {/* CLAUDE.md §4: her finansal çıktı bu ibareyi taşımak zorunda. */}
              <p className="m-0 text-center text-xs italic text-ink-soft dark:text-ink-faint">
                {INVESTMENT_DISCLAIMER}
              </p>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>,
    document.body,
  );
}
