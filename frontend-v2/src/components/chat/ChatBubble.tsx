import { MessageMarkdown } from "@/components/chat/MessageMarkdown";
import { PaperBoatThinking } from "@/components/paper-boat/PaperBoat";
import { useWordReveal } from "@/chat/useWordReveal";
import type { ChatMessage } from "@/types/finance";

/**
 * "VİRA düşünüyor" — yanıt balonunun İÇİNDE, markanın kendi kayığıyla.
 *
 * Önceden iki ayrı bekleme işareti vardı: akıştan önce mesaj listesinin
 * altında duran kayık, akış başlayınca balonun içinde yanıp sönen `▍`
 * imleci. İkisi ekranın iki ayrı yerinde, iki ayrı dille aynı şeyi
 * söylüyordu. Beklenen yanıtın yerinde tek bir işaret durması hem daha
 * sakin hem de nereye bakılacağını söylüyor.
 *
 * Nokta animasyonu KAPALI (`showDots={false}`): kayık zaten hareket ediyor
 * ve iki farklı tempodaki animasyon yan yana iki ayrı olay gibi okunuyor.
 * Göz hızlı olanı takip ediyor, o da söyleyecek şeyi olmayan yarısı.
 *
 * Bileşen kendi `role="status" aria-live="polite"` sarmalayıcısını
 * getiriyor; buraya ikinci bir canlı bölge eklenmemeli.
 */
function DusunuyorIsareti() {
  return (
    <PaperBoatThinking
      size={30}
      label="VİRA düşünüyor"
      showDots={false}
      className="text-[13px] font-medium text-white/80"
    />
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

  const isAiBubble = !isUser && !message.error;

  return (
    <div className={`flex animate-fadeUp flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <div className={isAiBubble ? "relative" : ""}>
        {isAiBubble && (
          // Baloncuğun arkasında ufak, marka rengiyle uyumlu bir highlight —
          // dashboard'daki mavi tonla (bkz. --color-brand) aynı kaynaktan,
          // temaya göre otomatik uyum sağlıyor.
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -left-2.5 -top-2.5 h-11 w-11 rounded-full bg-[color-mix(in_srgb,var(--color-brand)_25%,transparent)] blur-lg"
          />
        )}
        <div
          className={
            "relative max-w-[84%] rounded-[14px] px-[18px] py-3.5 text-sm leading-[1.65] " +
            (message.error
              ? "rounded-bl-[4px] border border-danger/30 bg-danger-tint text-ink-soft dark:border-transparent"
              : `${isUser ? "rounded-br-[4px]" : "rounded-bl-[4px]"} bg-brand text-white`)
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
                <p
                  className={`m-0 mt-1.5 text-[11.5px] italic ${message.error ? "text-ink-faint" : "text-white/70"}`}
                >
                  Yanıt tamamlanamadı, bağlantı kesildi.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
