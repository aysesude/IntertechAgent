import { useEffect, useRef, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import type { Holding } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { holdingTotals, lotValue, lotPnl, lotReturnPct, lotDaysHeld } from "@/utils/holdings";
import { formatTRY2, formatSignedTRY2, formatPct, formatDateDMY, formatQuantityByUnit, formatNumberTR } from "@/utils/format";
import { POSITIVE, NEGATIVE } from "@/utils/colors";
import { XIcon } from "@/components/icons";

interface HoldingReturnDetailProps {
  holding: Holding;
  onClose: () => void;
}

// Birim fiyat hassasiyeti enstrüman türüne göre — hisse için 2, altın/döviz/
// tahvil (küçük birim, oransal fiyat) için daha fazla. Sadece görsel biçim,
// hesaplamayı etkilemez (bkz. src/utils/holdings.ts, tam float ile çalışır).
const UNIT_PRICE_DIGITS: Record<string, number> = {
  adet: 2,
  gr: 2,
  $: 4,
  "€": 4,
  "₺": 4,
};

function formatUnitPrice(value: number, unitLabel: string): string {
  const digits = UNIT_PRICE_DIGITS[unitLabel] ?? 2;
  return "₺" + formatNumberTR(value, digits);
}

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function HoldingReturnDetail({ holding, onClose }: HoldingReturnDetailProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = `getiri-detay-baslik-${holding.id}`;

  // Açılışta odağı panele taşı, kapanışta önceki elemana geri ver —
  // ekran okuyucu ve klavye kullanıcıları için standart modal davranışı.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => previouslyFocused?.focus();
  }, []);

  // Panel açıkken arkadaki sayfa scroll'u kilitlenir — aksi halde arka plan
  // kayarken sabit panel yerinde durur ve ikisi görsel olarak birbirinden
  // kopar. Scrollbar kaybolunca sayfa genişliği artıp içerik kayacağı için
  // (Windows/Linux gibi overlay olmayan scrollbar'larda) o genişlik kadar
  // sağa padding eklenip telafi ediliyor.
  useEffect(() => {
    const { body, documentElement } = document;
    const scrollbarWidth = window.innerWidth - documentElement.clientWidth;
    const previousOverflow = body.style.overflow;
    const previousPaddingRight = body.style.paddingRight;
    body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`;
    }
    return () => {
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPaddingRight;
    };
  }, []);

  // Escape, panelin kendi onKeyDown'ına (odak-bağımlı bubbling) DEĞİL,
  // document seviyesindeki bir listener'a bağlı — odak henüz panele
  // taşınmamışken (mount anındaki kısa an) Escape'e basılırsa odağa bağlı
  // bubbling bunu bazen kaçırabiliyordu (canlı test edilip doğrulandı).
  // Document-level listener bu zamanlama riskini tamamen ortadan kaldırır.
  useEffect(() => {
    function handleEscape(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const root = panelRef.current;
    if (!root) return;
    const focusables = root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    // Odak trap: Tab ile son elemandan sonra ilk'e, Shift+Tab ile ilk
    // elemandan önce son'a döner — odak modalın dışına kaçmaz.
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  const totals = holdingTotals(holding.lots, holding.currentUnitPrice);

  // Portal ile document.body altına taşınıyor: HoldingsTable'ı saran Card
  // backdrop-blur-2xl kullanıyor — bazı tarayıcılarda backdrop-filter,
  // içindeki position:fixed elemanlar için yeni bir containing block
  // oluşturup modalı tüm ekran yerine kart sınırlarına hapsedebiliyor.
  // Portal bu riski tamamen ortadan kaldırır.
  return createPortal(
    <div className="fixed inset-0 z-[200] grid place-items-center p-4" onKeyDown={handleKeyDown}>
      <motion.div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 bg-[#0B0E14]/50 backdrop-blur-sm dark:bg-black/70"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      />

      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="relative z-10 w-full max-w-[560px] outline-none"
      >
        {/* Dikey flex kolon + overflow-hidden: başlık/özet ("shrink-0") hep
            görünür kalır, sadece parti listesi kendi alanında kayar. Kartın
            kendisi 85vh'i geçmez; overflow-hidden köşelerin yuvarlaklığını
            iç scrollbar'a rağmen korur. */}
        <Card className="flex max-h-[85vh] flex-col overflow-hidden">
          <button
            onClick={onClose}
            aria-label="Kapat"
            className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-lg text-ink-faint transition-colors hover:bg-line2 hover:text-ink"
          >
            <XIcon size={16} />
          </button>

          <div className="shrink-0">
            <h2 id={titleId} className="font-display m-0 pr-10 text-[19px] font-semibold">
              {holding.name}
            </h2>
            <p className="m-0 mt-0.5 text-[13px] text-ink-faint">{holding.assetClass}</p>

            {/* ÖZET — referans görselde yok, kullanıcı partileri kafasında
                toplamak zorunda kalmasın diye eklendi. Parti bloklarından
                ayrışsın diye zemin bir kademe daha belirgin. */}
            <div className="mt-4 grid grid-cols-2 gap-3.5 rounded-[12px] bg-[#F0F2F5] p-4 dark:bg-white/[0.05] sm:grid-cols-4">
              <SummaryItem label="Toplam Adet" value={formatQuantityByUnit(totals.totalQuantity, holding.unitLabel)} />
              <SummaryItem label="Toplam Değer" value={formatTRY2(totals.totalValue)} />
              <SummaryItem
                label="Olası K/Z"
                value={formatSignedTRY2(totals.totalPnl)}
                color={totals.totalPnl >= 0 ? POSITIVE : NEGATIVE}
              />
              <SummaryItem
                label="Ağırlıklı Getiri"
                value={formatPct(totals.weightedReturnPct)}
                color={totals.weightedReturnPct >= 0 ? POSITIVE : NEGATIVE}
              />
            </div>

            <div className="mt-5 text-[11px] font-semibold uppercase tracking-[.7px] text-ink-faint">
              Getiri Detayları
            </div>
          </div>

          {/* min-h-0 şart: flex item'ların varsayılan min-height'ı "auto"
              olduğu için onsuz bu alan içeriği kadar büyür ve overflow-y-auto
              hiç devreye girmez. Sağdaki p-6 (Card'ın kendi padding'i)
              scrollbar'ı listenin içine, kartın köşesinden içeride tutar.
              pr-2.5: macOS'un overlay scrollbar'ı yer kaplamadan içeriğin
              ÜSTÜNE biner — bu boşluk olmadan sağa hizalı değerlerin
              üzerine biniyordu. */}
          <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-2.5">
            <div className="flex flex-col gap-2.5 pb-1">
              {holding.lots.map((lot) => {
                const value = lotValue(lot, holding.currentUnitPrice);
                const pnl = lotPnl(lot, holding.currentUnitPrice);
                const returnPct = lotReturnPct(lot, holding.currentUnitPrice);
                const days = lotDaysHeld(lot);
                const tone = pnl >= 0 ? POSITIVE : NEGATIVE;
                return (
                  <div key={lot.id} className="rounded-[10px] bg-[#F7F8FA] p-3.5 dark:bg-white/[0.03]">
                    <DetailRow label="Alış Tarihi/Gün Sayısı" value={`${formatDateDMY(lot.purchaseDate)} - ${days} Gün`} />
                    <DetailRow label="Güncel Adet" value={formatQuantityByUnit(lot.quantity, holding.unitLabel)} />
                    <DetailRow label="Toplam Değer" value={formatTRY2(value)} />
                    <DetailRow label="Alış Birim Fiyatı" value={formatUnitPrice(lot.unitCost, holding.unitLabel)} />
                    <DetailRow label="Güncel Birim Fiyatı" value={formatUnitPrice(holding.currentUnitPrice, holding.unitLabel)} />
                    <DetailRow label="Olası Kâr/Zarar" value={formatSignedTRY2(pnl)} color={tone} />
                    <DetailRow label="Olası Getiri" value={formatPct(returnPct)} color={tone} />
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      </motion.div>
    </div>,
    document.body
  );
}

function SummaryItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[10.5px] font-semibold uppercase tracking-[.4px] text-ink-faint">{label}</div>
      <div className={`mt-1 text-[14px] font-semibold ${color ? "" : "text-ink"}`} style={color ? { color } : undefined}>
        {value}
      </div>
    </div>
  );
}

function DetailRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1 text-[13px]">
      <span className="text-ink-muted">{label}</span>
      <span className={`font-semibold ${color ? "" : "text-ink"}`} style={color ? { color } : undefined}>
        {value}
      </span>
    </div>
  );
}
