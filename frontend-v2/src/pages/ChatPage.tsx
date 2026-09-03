import { useState } from "react";
import { AssistantAvatar } from "@/components/chat/AssistantAvatar";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatGreeting } from "@/components/chat/ChatGreeting";
import { DownloadIcon, PlusIcon, SendIcon } from "@/components/icons";
import { useChat } from "@/chat/ChatProvider";
import { useScrollNewUserMessageToTop } from "@/chat/useScrollNewUserMessageToTop";
import { downloadTranscript } from "@/chat/transcript";
import { useAuth } from "@/auth/AuthContext";
import { useVisualViewportHeight } from "@/hooks/useVisualViewportHeight";
import { useScrollLock } from "@/hooks/useScrollLock";
import { INVESTMENT_DISCLAIMER, mockChatPage } from "@/data/mockData";

export function ChatPage() {
  const { messages, sending, sendMessage, resetSession } = useChat();
  const { user } = useAuth();
  const [draft, setDraft] = useState("");
  const getBubbleRef = useScrollNewUserMessageToTop(messages);
  // Mobilde ekran klavyesi açıldığında kartın klavyenin arkasında
  // kalmaması için — gerekçe hook'un kendi dosyasında.
  const vvhYenidenOlc = useVisualViewportHeight();
  // SAYFA (body) KİLİTLİ. iOS Safari, giriş kutusuna odaklanınca "yardımcı
  // olayım" diye SAYFANIN KENDİSİNİ kaydırıyor — bizim `overflow-y-auto`
  // mesaj kutumuzu değil. Sonuç: kart ekrandan tamamen kayıp arkada yalnızca
  // arka plan görseli kalıyordu ya da sayfa yanlara/aşağı zıplıyordu.
  // `useScrollLock` body'yi `position: fixed` yapıyor — artık kaydıracak bir
  // "sayfa" yok, tek kayan yüzey mesaj listesinin kendisi kalıyor (aynı
  // hook modallarda rubber-band kaymasını önlemek için kullanılıyor, bkz.
  // kendi dosyası — buradaki sebep de aynı aile).
  useScrollLock();

  // Giriş kutusu odaklanınca (klavye açılırken) sayfayı EN BAŞA sabitler VE
  // `--app-vvh`'yi elle tazeler. `useScrollLock` document scroll'unu
  // kilitlese de iOS Safari klavye açılışında "visual viewport"u (kaydırmadan
  // AYRI bir katman — bkz. useVisualViewportHeight.ts) hafifçe kaydırabiliyor;
  // ayrıca klavye AÇILIŞ ANİMASYONU sırasında `--app-vvh` ara (henüz
  // oturmamış) bir değerde donuk kalıp kart geçici olarak yanlış boyutlu
  // görünebiliyordu (bkz. hook'un kendi dosyasındaki not) — kullanıcı
  // yazmaya başlayana kadar (tesadüfen başka bir olay tetiklenene kadar)
  // öyle kalıyordu. İki çağrı: biri hemen (odaklanma anı), biri klavye
  // açılış animasyonu bittikten sonra (iOS'ta ~250-300ms) — ilk çağrı
  // animasyon başlamadan önce olduğu için tek başına yetmiyordu.
  const sayfayiEnBasaSabitle = () => {
    window.scrollTo(0, 0);
    vvhYenidenOlc();
    window.setTimeout(() => {
      window.scrollTo(0, 0);
      vvhYenidenOlc();
    }, 320);
  };

  const handleSend = (text?: string) => {
    const value = text ?? draft;
    if (!value.trim() || sending) return;
    void sendMessage(value);
    setDraft("");
  };

  return (
    /* SAYFA KAYMAZ, YALNIZCA AKIŞ KAYAR.
       Yükseklik görüntü alanına sabitleniyor (üstteki başlık çubuğu ve
       `main` dolgusu düşülerek), kart aradaki boşluğu `flex-1` ile
       dolduruyor. Önceden kart `h-[640px]` sabitti: kısa ekranlarda sayfanın
       kendisi kayıyordu, yani hem sayfa hem sohbet akışı kayan iki ayrı
       yüzeydi ve yazarken görüntü zıplıyordu.
       Yükseklik `useVisualViewportHeight`'in yazdığı `--app-vvh`
       değişkeninden geliyor (bkz. index.css .chat-viewport-height) — sabit
       `vh`/`dvh` DEĞİL, çünkü ikisi de MOBİL EKRAN KLAVYESİ açıldığında
       küçülmüyor: kart klavyenin ARKASINDA kalır, giriş kutusu görünmez
       olurdu. `visualViewport` klavye açıkken de gerçek görünür yüksekliği
       verdiği için kart klavyenin ÜSTÜNDE kalacak şekilde küçülüyor. */
    <div className="chat-viewport-height flex flex-col overflow-hidden">
      {/* Mobilde daha küçük/dar başlık: "Asistan" etiketinin alt boşluğu ve
          başlığın punto boyutu düşürüldü — kalan yükseklik doğrudan sohbet
          kartına gidiyor (bkz. .chat-viewport-height ve yukarıdaki düğme
          notları, aynı gerekçe). */}
      <div className="mb-3 flex flex-wrap items-end justify-between gap-4 sm:mb-5">
        <div>
          <div className="font-display mb-1 text-[11px] font-semibold uppercase tracking-[1.4px] text-navy sm:mb-2.5 sm:text-xs">
            Asistan
          </div>
          <h1 className="font-display m-0 text-xl font-bold tracking-[-1px] sm:text-[28px] lg:text-[34px]">
            AI Finans Danışmanı
          </h1>
        </div>
        <div className="flex gap-2">
          {/* GEÇİCİ — sunum öncesi test turu için. Sorulan soruları ve alınan
              yanıtları sırasıyla .txt olarak indirir; bozuk yanıtları elle
              kopyalamadan toplayabilmek için. Sunum sonrası kaldırılacak.
              Mobilde gizli: dar ekranda başlıkla aynı satıra sığmayıp alt
              satıra taşıyordu, bu da sohbet kartına ayrılan sabit
              yüksekliği kart aleyhine küçültüyordu (bkz. .chat-viewport-height
              üstteki not). Zaten kalıcı bir özellik değil. */}
          <button
            onClick={() => downloadTranscript(messages, user.name)}
            disabled={messages.length === 0}
            title="Bu sohbetteki tüm soru ve yanıtları .txt olarak indir"
            className="hidden h-11 items-center justify-center gap-1.5 rounded-[10px] border border-line px-4 text-[13.5px] font-semibold text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink-soft dark:border-transparent dark:bg-white/5 dark:text-ink-muted dark:disabled:hover:text-ink-muted sm:flex"
          >
            <DownloadIcon size={14} />
            Dökümü İndir
          </button>
          {/* "Yeni Sohbet" metni mobilde gizli, yalnızca ikon kalıyor: aynı
              satıra sığması (başlıkla yan yana) için — sığmayınca satır
              taşıp yukarıdaki gerekçeyle kartı küçültüyordu. */}
          <button
            onClick={resetSession}
            aria-label="Yeni Sohbet"
            className="flex h-11 items-center justify-center gap-1.5 rounded-[10px] border border-line px-3 text-[13.5px] font-semibold text-ink-soft transition-colors hover:border-brand hover:text-brand dark:border-transparent dark:bg-white/5 dark:text-ink-muted sm:px-4"
          >
            <PlusIcon size={14} />
            <span className="hidden sm:inline">Yeni Sohbet</span>
          </button>
        </div>
      </div>

      {/* Geçmiş kenar çubuğu KALDIRILDI: backend'de oturum listeleme ucu yok
          ve çalışmayan bir liste göstermek demoda soru işareti yaratır.
          Uç eklendiğinde geri gelecek. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-line bg-white dark:border-transparent dark:bg-surface-elevated dark:shadow-[0_8px_28px_-18px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.03)]">
        <div className="flex shrink-0 items-center gap-[11px] border-b border-line2 px-[22px] py-4 dark:border-transparent">
          <AssistantAvatar />
          <div className="flex-1">
            <div className="text-sm font-semibold">Vira Chat</div>
            <div className="text-xs text-ink-faint">Portföy verilerine bağlı · çevrimiçi</div>
          </div>
          <span className="h-2 w-2 animate-pulseDot rounded-full bg-brand" />
        </div>

        {/* `min-h-0` şart: flex çocuğunun varsayılan `min-height:auto` değeri
            içeriğin küçülmesini engeller ve kaydırma kutuya değil SAYFAYA
            taşardı. */}
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-[22px] py-6">
          {/* Karşılama akışın EN ÜSTÜNDE sabit durur ve `messages` dizisine
              GİRMEZ (gerekçesi ChatGreeting içinde). Mesaj gelince kaybolmaz:
              gerçek bir karşılama kaydırınca yukarıda kalır, kaybolan şey
              karşılama değil yer tutucu olurdu.

              Eski boş-durum metni ("Portföyünüz, riskiniz veya piyasa
              hakkında bir soru sorun.") kaldırıldı — karşılama onun işini
              zaten yapıyor ve altındaki öneri çipleri somut soruları
              veriyor. */}
          <ChatGreeting userName={user.name} />
          {messages.map((m) => (
            <ChatBubble key={m.id} message={m} ref={getBubbleRef(m)} />
          ))}
          {/* "VİRA düşünüyor…" artık BURADA DEĞİL, yanıt balonunun içinde
              (bkz. ChatBubble). Beklenen yanıtın yerinde durması, ekranın
              başka bir köşesinde durmasından daha anlaşılır. */}
        </div>

        {/* Mobilde gizli: üç öneri çipi dar ekranda 2-3 satıra sarıyor ve
            sabit yükseklikli (dvh) sohbet kartından mesaj alanının payına
            düşen alanı yiyordu — dar viewport'ta mesaj listesi neredeyse
            görünmez hale geliyordu. */}
        <div className="hidden shrink-0 flex-wrap gap-2 px-[22px] pb-2 sm:flex">
          {mockChatPage.suggestedPrompts.map((prompt) => (
            <button
              key={prompt}
              onClick={() => handleSend(prompt)}
              disabled={sending}
              className="min-h-10 rounded-full border-[1.5px] border-brand-border bg-white px-[15px] py-[9px] text-[12.5px] font-semibold text-brand transition-colors hover:bg-brand-tint disabled:cursor-not-allowed disabled:opacity-50 dark:border-transparent dark:bg-surface-elevated"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Giriş kutusunun üstünde duran maskot KALDIRILDI: kartın sağ alt
            köşesinde, yanıt akarken dikkati metinden çekiyordu. */}
        <div className="flex shrink-0 gap-2.5 border-t border-line2 px-[22px] pb-5 pt-3.5 dark:border-transparent">
          {/* GERÇEK SEBEP burasıydı — `text-sm` (14px) mobilde: iOS Safari,
              font-size'ı 16px'in ALTINDA olan bir input'a odaklanınca
              SAYFAYI OTOMATİK YAKINLAŞTIRIYOR (kullanıcı okuyabilsin diye).
              Bu yakınlaştırma, önceki "sayfa kayıyor/klavyenin arkasında
              kalıyor" şikâyetinin asıl kaynağıydı — body kilidi (yukarıdaki
              useScrollLock) BUNU önlemiyordu çünkü mekanizma sayfa kaydırma
              değil, tarayıcının kendi otomatik zoom'u. `text-base` (16px)
              bu tetikleyiciyi tamamen ortadan kaldırıyor; `sm:` üzerinde
              eski görünüm (14px) korunuyor, çünkü sorun yalnızca dokunmatik/
              iOS Safari'de var. */}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            onFocus={sayfayiEnBasaSabitle}
            disabled={sending}
            placeholder="Portföyün hakkında bir soru sor…"
            className="h-[46px] flex-1 rounded-[10px] border border-line px-4 text-base outline-none transition-shadow focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] disabled:opacity-60 dark:border-transparent dark:bg-white/[0.06] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#C4485A] dark:focus:shadow-[0_0_0_3px_rgba(196,72,90,.2)] sm:text-sm"
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
      <p className="m-0 mt-3 shrink-0 text-center text-xs italic text-ink-soft dark:text-ink-faint">
        {INVESTMENT_DISCLAIMER}
      </p>
    </div>
  );
}
