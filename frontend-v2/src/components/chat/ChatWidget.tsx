import { useState } from "react";
import { AssistantIcon } from "@/components/chat/AssistantAvatar";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatWidgetTitle } from "@/components/chat/ChatWidgetTitle";
import { BotIcon, SendIcon, SparkleIcon, XIcon } from "@/components/icons";
import { buildAssistantReply, mockWidgetStarterPrompts } from "@/data/mockData";
import type { ChatMessage } from "@/types/finance";
import { useTheme } from "@/context/ThemeContext";

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  // Widget her kapanışta sıfırlanır — sohbet geçmişi saklanmaz (BR-2), sadece
  // widget açıkken component state'inde tutulur.
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  const closeAndReset = () => {
    setOpen(false);
    setMessages([]);
    setDraft("");
    setSending(false);
  };

  const handleSend = (text?: string) => {
    const value = (text ?? draft).trim();
    if (!value) return;
    const userMessage: ChatMessage = {
      id: `w-${Date.now()}`,
      role: "user",
      text: value,
      createdAt: new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMessage]);
    setDraft("");
    setSending(true);
    setTimeout(() => {
      setMessages((prev) => [...prev, buildAssistantReply(value)]);
      setSending(false);
    }, 1100);
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
              onClick={closeAndReset}
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
                      className="min-h-10 rounded-full border-[1.5px] border-brand-border px-[13px] py-2 text-xs font-semibold text-brand hover:bg-brand-tint"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => <ChatBubble key={m.id} message={m} />)
            )}
            {sending && (
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

          <div className="flex shrink-0 gap-[9px] border-t border-line2 px-[18px] pb-[18px] pt-3">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Mesaj yaz…"
              className="h-11 flex-1 rounded-[10px] border border-line px-3.5 text-[13.5px] outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#C4485A] dark:focus:shadow-[0_0_0_3px_rgba(196,72,90,.2)]"
            />
            <button
              onClick={() => handleSend()}
              disabled={!draft.trim()}
              aria-label="Gönder"
              className="grid h-11 w-11 shrink-0 place-items-center rounded-[10px] bg-brand text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-faint disabled:hover:bg-line dark:bg-[#7A2B39] dark:hover:bg-[#8E3446]"
            >
              <SendIcon size={16} />
            </button>
          </div>
        </div>
      )}

      <div className={`fixed bottom-6 right-4 z-[61] w-[76px] flex-col items-center gap-1.5 sm:bottom-8 sm:right-8 ${open ? "hidden sm:flex" : "flex"}`}>
        <div className="relative h-16 w-16">
          <span className="animate-sonarPing pointer-events-none absolute inset-0 rounded-full border-2 border-[#8FB4F2] dark:border-[#C4485A]" />
          <button
            onClick={() => (open ? closeAndReset() : setOpen(true))}
            className="relative grid h-16 w-16 place-items-center overflow-hidden rounded-full border-2 border-[rgba(210,228,255,.85)] shadow-[0_10px_26px_rgba(24,72,176,.4),inset_0_2px_4px_rgba(255,255,255,.35)] transition-transform hover:scale-[1.08] dark:border-[rgba(196,72,90,.85)] dark:shadow-[0_10px_26px_rgba(122,43,57,.45),inset_0_2px_4px_rgba(255,255,255,.12)]"
            style={{
              background: isDark
                ? "radial-gradient(circle at 32% 28%, #C4485A, #7A2B39 62%, #5C2129)"
                : "radial-gradient(circle at 32% 28%, #3E7CE8, #1848B0 62%, #123C8E)",
            }}
            aria-label="Sohbeti aç/kapat"
          >
            {open ? (
              <XIcon size={24} className="text-white" />
            ) : (
              <AssistantIcon size={30} strokeWidth={2} className="text-white" />
            )}
          </button>
        </div>
        <span className="text-[11px] font-semibold text-white [text-shadow:0_1px_3px_rgba(15,17,21,.25)]">Asistan</span>
      </div>
    </>
  );
}
