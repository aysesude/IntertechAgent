import { useEffect, useRef, useState } from "react";
import { AssistantAvatar } from "@/components/chat/AssistantAvatar";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatInputRobot } from "@/components/chat/ChatInputRobot";
import { PaperBoatThinking } from "@/components/paper-boat/PaperBoat";
import { PlusIcon, SendIcon } from "@/components/icons";
import { useChatData } from "@/hooks/useChatData";

export function ChatPage() {
  const { data, messages, sending, sendMessage } = useChatData();
  const [draft, setDraft] = useState("");
  // Maskot yalnızca input'a ilk tıklandığında/odaklanıldığında bir kez
  // belirir ve öyle kalır — her yazma/blur döngüsünde animasyonun tekrar
  // tetiklenmesini önlemek için (bkz. kullanıcı geri bildirimi) bir daha
  // false'a dönmüyor.
  const [robotShown, setRobotShown] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const handleSend = (text?: string) => {
    const value = text ?? draft;
    if (!value.trim()) return;
    sendMessage(value);
    setDraft("");
  };

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <div className="mb-6">
        <div className="font-display mb-2.5 text-xs font-semibold uppercase tracking-[1.4px] text-navy">Asistan</div>
        <h1 className="font-display m-0 text-[32px] font-bold tracking-[-1px] sm:text-[38px]">AI Finans Danışmanı</h1>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[250px_1fr]">
        <div className="rounded-xl border border-line bg-white p-[18px] dark:border-transparent dark:bg-surface-elevated dark:shadow-[0_8px_28px_-18px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.03)]">
          <button className="mb-[18px] flex h-11 w-full items-center justify-center gap-1.5 rounded-[10px] bg-brand text-[13.5px] font-semibold text-white transition-colors hover:bg-brand-dark dark:bg-[#7A2B39] dark:hover:bg-[#8E3446]">
            <PlusIcon size={14} />
            Yeni Sohbet
          </button>
          <div className="mb-3 text-[11px] font-bold uppercase tracking-[.8px] text-ink-faint">Geçmiş</div>
          <div className="flex flex-col gap-1">
            {data.threads.map((thread) => (
              <div
                key={thread.id}
                className={
                  "rounded-[9px] px-3 py-[11px] text-[13px] transition-colors " +
                  (thread.active
                    ? "border border-brand-border bg-brand-tint font-semibold text-brand"
                    : "text-ink-muted hover:bg-[#F7F8FA] dark:hover:bg-white/5")
                }
              >
                {thread.title}
              </div>
            ))}
          </div>
        </div>

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
            {messages.map((m) => (
              <ChatBubble key={m.id} message={m} />
            ))}
            {sending && <PaperBoatThinking className="animate-fadeUp" label="VİRA düşünüyor…" />}
          </div>

          <div className="flex flex-wrap gap-2 px-[22px] pb-2">
            {data.suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => handleSend(prompt)}
                className="min-h-10 rounded-full border-[1.5px] border-brand-border bg-white px-[15px] py-[9px] text-[12.5px] font-semibold text-brand transition-colors hover:bg-brand-tint dark:bg-surface-elevated"
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
              placeholder="Portföyün hakkında bir soru sor…"
              className="h-[46px] flex-1 rounded-[10px] border border-line px-4 text-sm outline-none transition-shadow focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#C4485A] dark:focus:shadow-[0_0_0_3px_rgba(196,72,90,.2)]"
            />
            <button
              onClick={() => handleSend()}
              disabled={!draft.trim()}
              className="grid h-[46px] w-[46px] place-items-center rounded-[10px] bg-brand text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-faint disabled:hover:bg-line dark:bg-[#7A2B39] dark:hover:bg-[#8E3446]"
            >
              <SendIcon size={18} />
            </button>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
