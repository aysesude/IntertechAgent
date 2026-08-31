import { forwardRef } from "react";
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
 * Kayık 30'dan 40 piksele büyütüldü: salınım genliği boyuta oranlı, yani
 * küçükken hareket birkaç piksel kalıyor ve "bekliyor" mu "dondu" mu
 * anlaşılmıyordu. Etiket de 13 px'ten 14'e — balonun kendi metniyle aynı
 * boy, iki ayrı yazı ölçüsü yan yana durmasın.
 *
 * Bileşen kendi `role="status" aria-live="polite"` sarmalayıcısını
 * getiriyor; buraya ikinci bir canlı bölge eklenmemeli.
 */
function DusunuyorIsareti() {
  return (
    <PaperBoatThinking
      size={40}
      label="VİRA düşünüyor"
      showDots={false}
      className="text-sm font-medium text-ink-soft"
    />
  );
}

/**
 * VİRA'nın balonu — karşılama (`ChatGreeting`) ile ORTAK.
 *
 * İki yerde ayrı ayrı yazılsaydı biri değiştiğinde diğeri geride kalır ve
 * sohbette iki farklı tonda "asistan balonu" görünürdü.
 *
 * Nötr zemin, marka rengi DEĞİL. Kullanıcı ve asistan balonları aynı
 * `bg-brand` tonundaydı; kimin konuştuğu ancak hizadan anlaşılıyordu.
 * Ayrım için asistan tarafı nötr yapıldı, çünkü uzun olan taraf o: markdown
 * listeleri, tablolar ve rakamlar doygun bir zemin üzerinde yorucu okunuyor.
 * Vurgu rengi kısa olan tarafta, kullanıcının kendi mesajında kalıyor.
 */
export const AI_BALON_SINIFLARI = "rounded-bl-[4px] bg-line2 text-ink";

// `forwardRef`: gönderilen mesajı sekmenin başına kaydırabilmek için
// (bkz. ChatPage/ChatWidget'taki scroll efekti) çağıran tarafın dış
// `<div>`'e doğrudan erişmesi gerekiyor — ekstra bir sarmalayıcı `<div>`
// eklemek yerine (flex/gap düzenini bozardı) ref burada iletiliyor.
export const ChatBubble = forwardRef<HTMLDivElement, { message: ChatMessage }>(function ChatBubble(
  { message },
  ref,
) {
  const isUser = message.role === "user";

  // Ekranda görünen metin ağdan AYRI ilerler: token'lar düzensiz gelir,
  // gösterim sabit tempoda yetişir (bkz. useWordReveal).
  const gorunen = useWordReveal(isUser ? "" : message.text, message.streaming === true);

  // Henüz açılmış tek kelime yoksa balon boş görünürdü; bekleme işareti
  // hem ilk token'ı beklerken hem de ilk kelime açılana kadar durur.
  const dusunuyor = !isUser && message.streaming === true && gorunen.length === 0;

  const isAiBubble = !isUser && !message.error;

  return (
    <div ref={ref} className={`flex animate-fadeUp flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      {/* GENİŞLİK SINIRI BURADA, balonda değil.
          `max-w-[84%]` balonun kendisindeydi ve balonun kapsayan bloğu bu
          sarmalayıcı — genişliği ise içeriğe göre (shrink-to-fit) belirlenen
          bir kutu. Yüzde, kendisi içeriğe bağlı bir genişliğe göre
          çözülünce tarayıcı doğal metin genişliğinin %84'ünü uyguluyordu:
          bol yer varken bile KISA mesajlar ikinci satıra düşüyor, yalnızca
          bekleme işaretini taşıyan balon ise işarete dar geliyordu.
          Sarmalayıcı satırın tam genişliğine sahip olduğu için yüzde burada
          beklendiği gibi çözülüyor. %84 -> %90. */}
      <div className={`max-w-[90%] ${isAiBubble ? "relative" : ""}`}>
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
            "relative w-fit rounded-[14px] px-[18px] py-3.5 text-sm leading-[1.65] " +
            (message.error
              ? "rounded-bl-[4px] border border-danger/30 bg-danger-tint text-ink-soft dark:border-transparent"
              : isUser
                ? "rounded-br-[4px] bg-brand text-white"
                : AI_BALON_SINIFLARI)
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
                  className="m-0 mt-1.5 text-[11.5px] italic text-ink-faint"
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
});
