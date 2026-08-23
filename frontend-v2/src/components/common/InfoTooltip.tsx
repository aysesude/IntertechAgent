import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";

interface InfoTooltipProps {
  text: string;
}

/**
 * Kart başlıklarının yanına konan küçük "i" bilgilendirme ikonu.
 * Tıklanınca (hover değil — mobilde de çalışsın diye) açıklama metnini
 * içeren bir balon açar; dışarı tıklanınca kapanır.
 */
export function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (open && ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("click", handleClick, true);
    return () => document.removeEventListener("click", handleClick, true);
  }, [open]);

  return (
    <div className="relative inline-flex" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Bu bölüm hakkında bilgi"
        aria-expanded={open}
        className="grid h-5 w-5 place-items-center rounded-full text-ink-faint transition-colors hover:bg-brand-tint hover:text-brand"
      >
        <Info size={14} />
      </button>

      {open && (
        <div
          role="tooltip"
          className="animate-tipIn absolute left-1/2 top-[calc(100%+9px)] z-50 w-64 -translate-x-1/2 rounded-xl border border-line bg-white p-3 text-[12.5px] leading-[1.55] text-ink-soft shadow-pop dark:bg-surface-elevated"
        >
          {text}
          <div className="absolute -top-[5px] left-1/2 h-2.5 w-2.5 -translate-x-1/2 rotate-45 border-l border-t border-line bg-white dark:bg-surface-elevated" />
        </div>
      )}
    </div>
  );
}

export default InfoTooltip;
