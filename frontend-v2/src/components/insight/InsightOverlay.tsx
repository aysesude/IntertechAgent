import { useEffect, useRef, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
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
 * ERİŞİLEBİLİRLİK — İKİ AYRI KORUMA, ikisi de gerekli:
 *
 * 1. **Odak tuzağı.** Tab/Shift+Tab katmanın içinde döner, arka plandaki
 *    düğmelere kaçmaz. Kalıp `HoldingReturnDetail`'den geliyor (aynı
 *    `FOCUSABLE_SELECTOR`, aynı döngü); oraya ek olarak burada kapanışta
 *    odak, paneli AÇAN öğeye geri veriliyor — klavye kullanıcısı listenin
 *    başına fırlamamalı.
 * 2. **`inert`.** Arka plan yalnızca Tab sırasından değil, ERİŞİLEBİLİRLİK
 *    AĞACINDAN da çıkıyor: ekran okuyucu kullanıcısı bulanık arka plandaki
 *    içeriği hiç duymuyor. Odak tuzağı tek başına bunu yapmaz.
 *
 * React 18 `inert`'i prop olarak tanımıyor (React 19'da var), bu yüzden ref
 * üzerinden `setAttribute` ile veriliyor. Yükseltme GEREKMİYOR: çalışma
 * zamanı davranışı birebir aynı (karar, 2 Eylül 2026 — React 19'a geçmek
 * recharts/framer-motion/google-charts zincirini de yükseltmek demek ve
 * etki alanı her grafik + her sayfa geçişi).
 *
 * PORTAL: katman `document.body` altına taşınıyor. `HoldingReturnDetail`'in
 * gerekçesi burada da geçerli — `backdrop-filter` kullanan bir ata, içindeki
 * `position: fixed` elemanlar için yeni bir containing block oluşturabiliyor
 * ve katmanı tüm ekran yerine o kutunun içine hapsedebiliyor.
 */

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** Uygulama kapsayıcısı (bkz. `index.html`). Katman portal ile bunun DIŞINA
 *  çıktığı için `inert` doğrudan buna verilebiliyor. */
const UYGULAMA_KOKU_ID = "root";

interface InsightOverlayProps {
  open: boolean;
  onClose: () => void;
  /** Bulunulan sayfanın kartı açılışta geniş gelir. */
  activeCardId: InsightCardId;
}

export function InsightOverlay({ open, onClose, activeCardId }: InsightOverlayProps) {
  const { cards, loading, error } = useInsightData(open);
  const panelRef = useRef<HTMLDivElement>(null);

  // `onClose` REF'TE TUTULUYOR, bağımlılık listesinde DEĞİL.
  //
  // Çağıran taraf onu satır içi ok fonksiyonu olarak veriyor (her render'da
  // yeni bir kimlik). Bağımlılıkta kalsaydı ebeveynin her render'ında efekt
  // temizlenip yeniden kurulurdu: `inert` bir an kalkıp geri gelir ve
  // temizlikteki odak geri verme her seferinde çalışırdı — panel açıkken
  // odak, paneli açan düğmeye sıçrardı.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;

    const kapat = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", kapat);

    const oncekiOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Arka plan erişilebilirlik ağacından da çıkar (bkz. bileşen
    // docstring'i, 2. madde). React 18 `inert`'i prop olarak tanımadığı için
    // öznitelik elle veriliyor.
    const kok = document.getElementById(UYGULAMA_KOKU_ID);
    kok?.setAttribute("inert", "");

    // Paneli AÇAN öğe: kapanışta odak buraya geri verilecek.
    const oncekiOdak = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", kapat);
      document.body.style.overflow = oncekiOverflow;
      kok?.removeAttribute("inert");
      // `inert` kalkmadan odak verilemez: inert bir ağaçtaki öğe odak alamaz.
      oncekiOdak?.focus?.();
    };
  }, [open]);

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
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Hızlı Özet"
        tabIndex={-1}
        onKeyDown={odagiTut}
        className="fixed inset-0 z-[200] flex flex-col items-center justify-center gap-6 bg-white/55 px-4 py-10 outline-none backdrop-blur-2xl dark:bg-[#050B12]/60"
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
    </>,
    document.body,
  );
}
