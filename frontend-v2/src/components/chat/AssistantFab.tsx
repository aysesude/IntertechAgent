import { useEffect, useRef, useState } from "react";
import type { InsightCardId } from "@/api/insight";
import { AssistantIcon } from "@/components/chat/AssistantAvatar";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { SparkleIcon, XIcon } from "@/components/icons";
import { InsightOverlay } from "@/components/insight/InsightOverlay";
import { useTheme } from "@/context/ThemeContext";

/**
 * Yüzen asistan düğmesi — Material Design 3'teki FAB menü kalıbı.
 *
 * Düğme artık tek bir panele değil İKİ ayrı yüzeye açılıyor:
 *   • Hızlı Özet  → `InsightOverlay` (dört kart)
 *   • Mini sohbet → `ChatWidget` (sayfa içi sohbet paneli)
 *
 * "Asistan" yazısı KALDIRILDI: iki eylem menüde adlarıyla duruyor, düğmenin
 * altındaki etiket artık bilgi taşımıyordu.
 *
 * MENÜ YALNIZCA TIKLAMAYLA AÇILIR. Önce hover ile de açılıyordu; sahada
 * ölçüldü (2 Eylül 2026): menü fare imlecinin ALTINDA belirdiği için
 * kullanıcı daha ne olduğunu görmeden bir eyleme tıklamış oluyor, sonra da
 * kapatıyordu. Hover'ın kazandırdığı tek şey bir tıklamaydı; kaybettirdiği
 * şey kontroldü.
 *
 * BASILI TUTMA YOK — bilerek. Keşfedilebilirliği sıfır (kimse denemez) ve
 * kayıtlı demo videolarında izleyici ne yapıldığını göremez: ekranda bir şey
 * açılır, sebebi anlaşılmaz.
 */

interface AssistantFabProps {
  /** Bulunulan sayfanın kartı özet panelinde açılışta geniş gelir. */
  activeCardId: InsightCardId;
}

export function AssistantFab({ activeCardId }: AssistantFabProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const [menuAcik, setMenuAcik] = useState(false);
  const [sohbetAcik, setSohbetAcik] = useState(false);
  const [ozetAcik, setOzetAcik] = useState(false);
  const kapsayici = useRef<HTMLDivElement>(null);

  // Dışarı tıklama ve Esc menüyü kapatır.
  useEffect(() => {
    if (!menuAcik) return;

    const disariTikla = (e: MouseEvent) => {
      if (!kapsayici.current?.contains(e.target as Node)) setMenuAcik(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuAcik(false);
    };
    document.addEventListener("mousedown", disariTikla);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", disariTikla);
      document.removeEventListener("keydown", esc);
    };
  }, [menuAcik]);

  const eylemSec = (eylem: "ozet" | "sohbet") => {
    setMenuAcik(false);
    if (eylem === "ozet") setOzetAcik(true);
    else setSohbetAcik(true);
  };

  const panelAcik = sohbetAcik || ozetAcik;

  return (
    <>
      <ChatWidget open={sohbetAcik} onClose={() => setSohbetAcik(false)} />
      <InsightOverlay
        open={ozetAcik}
        onClose={() => setOzetAcik(false)}
        activeCardId={activeCardId}
      />

      {/* Bir panel açıkken düğme tamamen gizleniyor: panelin kendi kapat
          düğmesi varken sağ altta ikinci bir "çarpı" göstermek kafa
          karıştırıyordu (önceki sürümde ölçüldü). */}
      <div
        ref={kapsayici}
        className={`fixed bottom-6 right-4 z-[150] flex-col items-end gap-2 sm:bottom-8 sm:right-8 ${
          panelAcik ? "hidden" : "flex"
        }`}
      >
        {menuAcik && (
          <div className="flex animate-fadeUp flex-col items-end gap-2">
            <FabEylem
              etiket="Hızlı özet"
              onClick={() => eylemSec("ozet")}
              ikon={<SparkleIcon size={18} />}
            />
            <FabEylem
              etiket="Mini sohbet"
              onClick={() => eylemSec("sohbet")}
              ikon={<AssistantIcon size={18} strokeWidth={2} />}
            />
          </div>
        )}

        <button
          onClick={() => setMenuAcik((v) => !v)}
          aria-label="Asistan menüsü"
          aria-expanded={menuAcik}
          // Sayfanın camsı kart yüzeyiyle aynı şeffaflık/blur/gölge seviyesi
          // (bkz. Card.tsx CARD_SURFACE_CLASS).
          className="grid h-16 w-16 place-items-center rounded-full border border-[rgba(15,23,42,0.08)] shadow-[0_10px_30px_-20px_rgba(15,23,42,0.12)] backdrop-blur-[16px] transition-transform hover:scale-[1.04] dark:border-transparent dark:shadow-[0_10px_30px_-18px_rgba(0,0,0,0.55)]"
          style={{ backgroundColor: isDark ? "rgba(196,72,90,0.82)" : "rgba(37,87,232,0.68)" }}
        >
          {menuAcik ? (
            <XIcon size={22} className="text-white" />
          ) : (
            <AssistantIcon size={30} strokeWidth={2} className="text-white" />
          )}
        </button>
      </div>
    </>
  );
}

function FabEylem({
  etiket,
  onClick,
  ikon,
}: {
  etiket: string;
  onClick: () => void;
  ikon: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2.5 rounded-full border border-line bg-white/90 py-2.5 pl-4 pr-3.5 text-[13px] font-semibold text-ink shadow-pop backdrop-blur-xl transition-colors hover:border-brand/50 dark:border-transparent dark:bg-[#0B151E]/90 dark:text-[#EDF1F7]"
    >
      {etiket}
      <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-tint text-brand">
        {ikon}
      </span>
    </button>
  );
}
