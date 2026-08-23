import { MessageMarkdown } from "@/components/chat/MessageMarkdown";
import { useWordReveal } from "@/chat/useWordReveal";
import type { ChatMessage } from "@/types/finance";

/**
 * "VİRA düşünüyor…" — yanıt balonunun İÇİNDE.
 *
 * Önceden iki ayrı bekleme işareti vardı: akıştan önce mesaj listesinin
 * altında duran kayık, akış başlayınca balonun içinde yanıp sönen `▍`
 * imleci. İkisi ekranın iki ayrı yerinde, iki ayrı dille aynı şeyi
 * söylüyordu. Beklenen yanıtın yerinde tek bir işaret durması hem daha
 * sakin hem de nereye bakılacağını söylüyor.
 */
function DusunuyorIsareti() {
  return (
    <span className="flex items-center gap-2 text-ink-faint" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        <span className="h-1.5 w-1.5 animate-thinkingDot rounded-full bg-current" />
        <span className="h-1.5 w-1.5 animate-thinkingDot rounded-full bg-current [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-thinkingDot rounded-full bg-current [animation-delay:300ms]" />
      </span>
      <span className="text-[13px] font-medium">VİRA düşünüyor…</span>
    </span>
  );
}

export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  // Ekranda görünen metin ağdan AYRI ilerler: token'lar düzensiz gelir,
  // gösterim sabit tempoda yetişir (bkz. useWordReveal).
  const gorunen = useWordReveal(isUser ? "" : message.text, message.streaming === true);

  // Henüz açılmış tek kelime yoksa balon boş görünürdü; bekleme işareti
  // hem ilk token'ı beklerken hem de ilk kelime açılana kadar durur.
  const dusunuyor = !isUser && message.streaming === true && gorunen.length === 0;

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
            {dusunuyor && <DusunuyorIsareti />}
            {gorunen && <MessageMarkdown text={gorunen} />}
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
