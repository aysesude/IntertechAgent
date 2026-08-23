import type { ChatMessage } from "@/types/finance";

export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex animate-fadeUp flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={
          "max-w-[84%] rounded-[14px] px-[18px] py-3.5 text-sm leading-[1.65] " +
          (isUser ? "rounded-br-[4px] bg-brand text-white" : "rounded-bl-[4px] bg-[#F5F6F8] text-ink-soft dark:bg-white/10")
        }
      >
        {message.text}
      </div>
    </div>
  );
}
