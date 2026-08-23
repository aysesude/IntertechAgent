import { useEffect, useRef, useState } from "react";
import { AssistantAvatar } from "@/components/chat/AssistantAvatar";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatInputRobot } from "@/components/chat/ChatInputRobot";
import { PaperBoatThinking } from "@/components/paper-boat/PaperBoat";
import { PlusIcon, SendIcon } from "@/components/icons";
import { useChat } from "@/chat/ChatProvider";
import { INVESTMENT_DISCLAIMER, mockChatPage } from "@/data/mockData";

export function ChatPage() {
  const { messages, sending, sendMessage, resetSession } = useChat();
  const [draft, setDraft] = useState("");
  // Maskot yalnızca input'a ilk odaklanıldığında bir kez belirir ve öyle
  // kalır — her yazma/blur döngüsünde animasyonun tekrar tetiklenmemesi için.
  const [robotShown, setRobotShown] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const handleSend = (text?: string) => {
    const value = text ?? draft;
    if (!value.trim() || sending) return;
    void sendMessage(value);
    setDraft("");
  };

  // "Düşünüyor" göstergesi YALNIZCA ilk token gelene kadar: token'lar akmaya
  // başladıktan sonra hem kayık hem yazan metin görünürse ekran iki ayrı
  // "bekle" sinyali verir.
  const sonMesaj = messages[messages.length - 1];
  const cevapBekleniyor = sending && sonMesaj?.role === "assistant" && sonMesaj.text === "";

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="font-display mb-2.5 text-xs font-semibold uppercase tracking-[1.4px] text-navy">
              Asistan
            </div>
            <h1 className="font-display m-0 text-[32px] font-bold tracking-[-1px] sm:text-[38px]">
              AI Finans Danışmanı
            </h1>
          </div>
          <button
            onClick={resetSession}
            className="flex h-11 items-center justify-center gap-1.5 rounded-[10px] border border-line px-4 text-[13.5px] font-semibold text-ink-muted transition-colors hover:border-brand hover:text-brand"
          >
            <PlusIcon size={14} />
            Yeni Sohbet
          </button>
        </div>

        {/* Geçmiş kenar çubuğu KALDIRILDI: backend'de oturum listeleme ucu yok
            ve çalışmayan bir liste göstermek demoda soru işareti yaratır.
            Uç eklendiğinde geri gelecek. */}
        <div className="flex h-[640px] flex-col overflow-hidden rounded-xl border border-line bg-white dark:border-transparent dark:bg-surface-elevated dark:shadow-[0_8px_28px_-18px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.03)]">
          <div className="flex items-center gap-[11px] border-b border-line2 px-[22px] py-4">
            <AssistantAvatar />
            <div className="flex-1">
              <div className="text-sm font-semibold">AI Asistan</div>
              <div className="text-xs text-ink-faint">Portföy verilerine bağlı · çevrimiçi</div>
            </div>
            <span className="h-2 w-2 animate-pulseDot rounded-full bg-brand" />
          </div>

          <div ref={scrollRef} className="flex flex-1 flex-col gap-4 overflow-y-auto px-[22px] py-6">
            {messages.length === 0 && (
              <p className="m-0 text-sm text-ink-faint">
                Portföyünüz, riskiniz veya piyasa hakkında bir soru sorun.
              </p>
            )}
            {messages.map((m) => (
              <ChatBubble key={m.id} message={m} />
            ))}
            {cevapBekleniyor && <PaperBoatThinking className="animate-fadeUp" label="VİRA düşünüyor…" />}
          </div>

          <div className="flex flex-wrap gap-2 px-[22px] pb-2">
            {mockChatPage.suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => handleSend(prompt)}
                disabled={sending}
                className="min-h-10 rounded-full border-[1.5px] border-brand-border bg-white px-[15px] py-[9px] text-[12.5px] font-semibold text-brand transition-colors hover:bg-brand-tint disabled:cursor-not-allowed disabled:opacity-50 dark:bg-surface-elevated"
              >
                {prompt}
              </button>
            ))}
          </div>

          <div className="relative flex gap-2.5 border-t border-line2 px-[22px] pb-5 pt-3.5">
            <ChatInputRobot visible={robotShown || sending} thinking={sending} leaning={draft.length > 0} />
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              onFocus={() => setRobotShown(true)}
              disabled={sending}
              placeholder="Portföyün hakkında bir soru sor…"
              className="h-[46px] flex-1 rounded-[10px] border border-line px-4 text-sm outline-none transition-shadow focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] disabled:opacity-60 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#C4485A] dark:focus:shadow-[0_0_0_3px_rgba(196,72,90,.2)]"
            />
            <button
              onClick={() => handleSend()}
              disabled={!draft.trim() || sending}
              className="grid h-[46px] w-[46px] place-items-center rounded-[10px] bg-brand text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-faint disabled:hover:bg-line dark:bg-[#7A2B39] dark:hover:bg-[#8E3446]"
            >
              <SendIcon size={18} />
            </button>
          </div>
        </div>

        {/* CLAUDE.md §4: her finansal çıktı bu ibareyi taşımak zorunda.
            Ajan metnin içinde de veriyor; burası sunum katmanının garantisi. */}
        <p className="m-0 mt-4 text-center text-xs italic text-ink-faint">{INVESTMENT_DISCLAIMER}</p>
      </div>
    </div>
  );
}
