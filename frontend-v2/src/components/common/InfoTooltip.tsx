import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

interface InfoTooltipProps {
  text: string;
}

const GAP_PX = 9;
const WIDTH_PX = 256; // w-64
const VIEWPORT_MARGIN_PX = 12;

interface Coords {
  top: number;
  left: number;
  /** Balonun içindeki ok işaretinin sol kenardan uzaklığı (ikonu göstermeye devam etsin diye). */
  caretLeft: number;
}

/**
 * Kart başlıklarının yanına konan küçük "i" bilgilendirme ikonu.
 * Tıklanınca (hover değil — mobilde de çalışsın diye) açıklama metnini
 * içeren bir balon açar; dışarı tıklanınca kapanır.
 */
export function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Balon document.body'ye portallanıp `position: fixed` ile ikonun gerçek
  // viewport koordinatına yerleştiriliyor. Önceden Card içinde absolute +
  // z-50'ydi; ama Card'ın backdrop-blur'u her Card'ı KENDİ stacking
  // context'i yapıyor (filtre/backdrop-filter'ın CSS'te bilinen etkisi) —
  // bu yüzden z-index yalnızca aynı Card içinde işe yarıyor, komşu bir
  // Card DOM'da sonra geldiğinde z-index'ten bağımsız olarak üstüne
  // biniyordu ("arkada kalma"). Portal bu izolasyonu tamamen ortadan
  // kaldırır. Sağ/sol kenara yakın ikonlarda balon ekran dışına taşmasın
  // diye viewport'a göre kırpılıyor; ok işareti de gerçek ikon merkezini
  // göstermeye devam etsin diye ayrıca hesaplanıyor.
  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const idealLeft = rect.left + rect.width / 2 - WIDTH_PX / 2;
    const left = Math.min(
      Math.max(idealLeft, VIEWPORT_MARGIN_PX),
      window.innerWidth - WIDTH_PX - VIEWPORT_MARGIN_PX,
    );
    const caretLeft = Math.min(Math.max(rect.left + rect.width / 2 - left, 16), WIDTH_PX - 16);
    setCoords({ top: rect.bottom + GAP_PX, left, caretLeft });
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || tooltipRef.current?.contains(target)) return;
      setOpen(false);
    }
    // `fixed` balon, sayfa ya da bir tablo/kart içi kaydırıldığında ikonu
    // takip etmez — yeniden hesaplamak yerine kapatmak en basit ve
    // güvenilir çözüm (yaygın "floating" bileşen davranışı).
    function handleScrollOrResize() {
      setOpen(false);
    }

    document.addEventListener("click", handleClick, true);
    window.addEventListener("scroll", handleScrollOrResize, true);
    window.addEventListener("resize", handleScrollOrResize);
    return () => {
      document.removeEventListener("click", handleClick, true);
      window.removeEventListener("scroll", handleScrollOrResize, true);
      window.removeEventListener("resize", handleScrollOrResize);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Bu bölüm hakkında bilgi"
        aria-expanded={open}
        className="grid h-5 w-5 place-items-center rounded-full text-ink-faint transition-colors hover:bg-brand-tint hover:text-brand"
      >
        <Info size={14} />
      </button>

      {open &&
        coords &&
        createPortal(
          <div
            ref={tooltipRef}
            role="tooltip"
            style={{ top: coords.top, left: coords.left, width: WIDTH_PX }}
            className="animate-tipIn fixed z-[300] rounded-xl border border-line bg-white p-3 text-[12.5px] leading-[1.55] text-ink-soft shadow-pop dark:border-transparent dark:bg-surface-elevated"
          >
            {text}
            <div
              className="absolute -top-[5px] h-2.5 w-2.5 rotate-45 border-l border-t border-line bg-white dark:border-transparent dark:bg-surface-elevated"
              style={{ left: coords.caretLeft - 5 }}
            />
          </div>,
          document.body,
        )}
    </>
  );
}

export default InfoTooltip;
