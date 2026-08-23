import { MessageMarkdown } from "@/components/chat/MessageMarkdown";
import type { ChatMessage } from "@/types/finance";

export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex animate-fadeUp flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={
          "max-w-[84%] rounded-[14px] px-[18px] py-3.5 text-sm leading-[1.65] " +
          (isUser
            ? "rounded-br-[4px] bg-brand text-white"
            : message.error
              ? "rounded-bl-[4px] border border-danger/30 bg-danger-tint text-ink-soft"
              : "rounded-bl-[4px] bg-[#F5F6F8] text-ink-soft dark:bg-white/10")
        }
      >
        {isUser ? (
          // Kullanıcının yazdığı metin markdown olarak YORUMLANMAZ: yazdığı
          // karakterler ne ise ekranda o görünmeli.
          message.text
        ) : (
          <>
            {message.text && <MessageMarkdown text={message.text} />}
            {message.streaming && (
              <span className="ml-0.5 animate-pulse" aria-hidden="true">
                ▍
              </span>
            )}
            {message.error && (
              <p className="m-0 text-[13px] font-medium text-danger">{message.error}</p>
            )}
            {message.incomplete && (
              // Akış tamamlanmadan koptu: elde kalan metin gösteriliyor ama
              // eksik olduğu söylenmeli, yarım cevap tam sanılmasın.
              <p className="m-0 mt-1.5 text-[11.5px] italic text-ink-faint">
                Yanıt tamamlanamadı, bağlantı kesildi.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
