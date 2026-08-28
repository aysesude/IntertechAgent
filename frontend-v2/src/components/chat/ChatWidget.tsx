import { useState } from "react";
import { AssistantIcon } from "@/components/chat/AssistantAvatar";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatWidgetTitle } from "@/components/chat/ChatWidgetTitle";
import { BotIcon, SendIcon, SparkleIcon, XIcon } from "@/components/icons";
import { INVESTMENT_DISCLAIMER, mockWidgetStarterPrompts } from "@/data/mockData";
import { useChat } from "@/chat/ChatProvider";
import { useTheme } from "@/context/ThemeContext";

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  // Widget ve AI Chat sayfası AYNI oturumu paylaşıyor (bkz. ChatProvider):
  // widget'ta başlayan konuşma sayfada devam eder ve ajan önceki mesajları
  // bağlam olarak görür. Bu yüzden kapanışta mesajlar SİLİNMİYOR — sadece
  // panel kapanıyor.
  const { messages, sending, sendMessage } = useChat();
  const [draft, setDraft] = useState("");

  // Üç nokta göstergesi yalnızca ilk token gelene kadar; sonrasında metin
  // zaten yazılıyor ve iki ayrı "bekle" sinyali göstermek gerekmiyor.
  const sonMesaj = messages[messages.length - 1];
  const cevapBekleniyor = sending && sonMesaj?.role === "assistant" && sonMesaj.text === "";

  const handleSend = (text?: string) => {
    const value = (text ?? draft).trim();
    if (!value || sending) return;
    void sendMessage(value);
    setDraft("");
  };

  return (
    <>
      {open && (
        <div className="animate-slideUpPanel fixed inset-x-4 top-4 bottom-4 z-[60] flex flex-col overflow-hidden rounded-[14px] border border-line bg-white/[0.72] backdrop-blur-2xl shadow-widget dark:border-transparent dark:bg-[#0B151E]/[0.72] dark:shadow-[0_28px_70px_-24px_rgba(0,0,0,0.65),0_0_0_1px_rgba(255,255,255,0.04)] sm:inset-x-auto sm:top-auto sm:bottom-[104px] sm:right-8 sm:h-auto sm:w-[376px] sm:max-w-[calc(100vw-2rem)]">
          <div className="flex shrink-0 items-center gap-[11px] bg-[#234FA2] px-[18px] py-4 dark:bg-[#7A2B39]">
            <span className="grid h-8 w-8 place-items-center rounded-[9px] bg-white/18 text-white">
              <BotIcon size={16} />
            </span>
            <div className="flex-1 text-white">
              <ChatWidgetTitle />
              <div className="text-[11.5px] opacity-80">Genelde birkaç saniyede yanıtlar</div>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Sohbeti kapat"
              className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-white/16 text-white transition-colors hover:bg-white/30"
            >
              <XIcon size={15} />
            </button>
          </div>

          <div className="flex flex-1 flex-col gap-3.5 overflow-y-auto px-[18px] py-5 sm:max-h-[300px] sm:flex-none">
            {messages.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-4 py-4 text-center">
                <span className="grid h-11 w-11 place-items-center rounded-full bg-brand-tint text-brand">
                  <SparkleIcon size={20} />
                </span>
                <div>
                  <div className="text-sm font-semibold">Sana nasıl yardımcı olabilirim?</div>
                  <p className="m-0 mt-1 text-[12.5px] text-ink-faint">Başlamak için bir soru seç veya kendi sorunu yaz.</p>
                </div>
                <div className="flex flex-col gap-2 self-stretch">
                  {mockWidgetStarterPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => handleSend(prompt)}
                      disabled={sending}
                      className="min-h-10 rounded-full border-[1.5px] border-brand-border px-[13px] py-2 text-xs font-semibold text-brand hover:bg-brand-tint dark:border-transparent dark:bg-white/5"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => <ChatBubble key={m.id} message={m} />)
            )}
            {cevapBekleniyor && (
              <div className="flex">
                <div className="flex items-center gap-1 rounded-[12px] rounded-bl-[4px] bg-[#F5F6F8] px-[15px] py-3 dark:bg-white/10">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-1.5 w-1.5 rounded-full bg-ink-faint"
                      style={{ animation: "pulseDot 1s ease-in-out infinite", animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex shrink-0 gap-[9px] border-t border-line2 px-[18px] pb-[18px] pt-3 dark:border-transparent">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              disabled={sending}
              placeholder="Mesaj yaz…"
              className="h-11 flex-1 rounded-[10px] border border-line px-3.5 text-[13.5px] outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] dark:border-transparent dark:bg-white/[0.06] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#C4485A] dark:focus:shadow-[0_0_0_3px_rgba(196,72,90,.2)]"
            />
            <button
              onClick={() => handleSend()}
              disabled={!draft.trim() || sending}
              aria-label="Gönder"
              className="grid h-11 w-11 shrink-0 place-items-center rounded-[10px] bg-brand text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-faint disabled:hover:bg-line dark:bg-[#7A2B39] dark:hover:bg-[#8E3446]"
            >
              <SendIcon size={16} />
            </button>
          </div>

          {/* CLAUDE.md §4: her finansal çıktı bu ibareyi taşımak zorunda.
              Kural SUNUM katmanında karşılanıyor — her mesajın sonuna
              gömülmüyor (orchestrator o talimatı bilerek kaldırdı, tekrar
              gürültüydü). Ama widget, Portföy ve Piyasa ekranlarında TEK
              sohbet yüzeyi ve burada hiçbir ibare yoktu: o sayfalarda
              kullanıcı finansal yanıt alıp uyarıyı hiç görmüyordu. */}
          <p className="m-0 shrink-0 px-[18px] pb-3 text-center text-[10.5px] italic leading-tight text-ink-faint">
            {INVESTMENT_DISCLAIMER}
          </p>
        </div>
      )}

      {/* Panel açıkken yüzen buton BİLEREK tamamen gizleniyor (masaüstünde
          de) — önceden `sm:flex` ile masaüstünde açıkken de görünüyordu ve
          X ikonuna dönüşüyordu; panelin kendi başlığındaki kapat düğmesiyle
          (yukarıda) birlikte sağ üstte İKİ ayrı "çarpı" oluşuyordu. */}
      <div className={`fixed bottom-6 right-4 z-[61] w-[76px] flex-col items-center gap-1.5 sm:bottom-8 sm:right-8 ${open ? "hidden" : "flex"}`}>
        <button
          onClick={() => setOpen((v) => !v)}
          // Sayfanın camsı kart yüzeyiyle (bkz. Card.tsx CARD_SURFACE_CLASS)
          // aynı şeffaflık/blur/gölge seviyesi — marka rengi zeminde
          // gradyan/parlama yerine ince bir ton olarak kalıyor.
          className="grid h-16 w-16 place-items-center rounded-full border border-[rgba(15,23,42,0.08)] shadow-[0_10px_30px_-20px_rgba(15,23,42,0.12)] backdrop-blur-[16px] transition-transform hover:scale-[1.04] dark:border-transparent dark:shadow-[0_10px_30px_-18px_rgba(0,0,0,0.55)]"
          style={{ backgroundColor: isDark ? "rgba(196,72,90,0.82)" : "rgba(37,87,232,0.68)" }}
          aria-label="Sohbeti aç/kapat"
        >
          {open ? (
            <XIcon size={24} className="text-white" />
          ) : (
            <AssistantIcon size={30} strokeWidth={2} className="text-white" />
          )}
        </button>
        <span className="text-[11px] font-semibold text-white [text-shadow:0_1px_3px_rgba(15,17,21,.25)]">Asistan</span>
      </div>
    </>
  );
}
