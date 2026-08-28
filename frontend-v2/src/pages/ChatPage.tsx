import { useEffect, useRef, useState } from "react";
import { AssistantAvatar } from "@/components/chat/AssistantAvatar";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { ChatGreeting } from "@/components/chat/ChatGreeting";
import { DownloadIcon, PlusIcon, SendIcon } from "@/components/icons";
import { useChat } from "@/chat/ChatProvider";
import { downloadTranscript } from "@/chat/transcript";
import { useAuth } from "@/auth/AuthContext";
import { INVESTMENT_DISCLAIMER, mockChatPage } from "@/data/mockData";

export function ChatPage() {
  const { messages, sending, sendMessage, resetSession } = useChat();
  const { user } = useAuth();
  const [draft, setDraft] = useState("");
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

  return (
    /* SAYFA KAYMAZ, YALNIZCA AKIŞ KAYAR.
       Yükseklik görüntü alanına sabitleniyor (üstteki başlık çubuğu ve
       `main` dolgusu düşülerek), kart aradaki boşluğu `flex-1` ile
       dolduruyor. Önceden kart `h-[640px]` sabitti: kısa ekranlarda sayfanın
       kendisi kayıyordu, yani hem sayfa hem sohbet akışı kayan iki ayrı
       yüzeydi ve yazarken görüntü zıplıyordu.
       `dvh` bilerek `vh` yerine: mobil tarayıcıda adres çubuğu gizlenince
       `vh` değişmez ve kartın altı ekranın dışında kalır. */
    <div className="flex h-[calc(100dvh-112px)] flex-col overflow-hidden sm:h-[calc(100dvh-140px)]">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="font-display mb-2.5 text-xs font-semibold uppercase tracking-[1.4px] text-navy">
            Asistan
          </div>
          <h1 className="font-display m-0 text-[28px] font-bold tracking-[-1px] sm:text-[34px]">
            AI Finans Danışmanı
          </h1>
        </div>
        <div className="flex gap-2">
          {/* GEÇİCİ — sunum öncesi test turu için. Sorulan soruları ve alınan
              yanıtları sırasıyla .txt olarak indirir; bozuk yanıtları elle
              kopyalamadan toplayabilmek için. Sunum sonrası kaldırılacak. */}
          <button
            onClick={() => downloadTranscript(messages, user.name)}
            disabled={messages.length === 0}
            title="Bu sohbetteki tüm soru ve yanıtları .txt olarak indir"
            className="flex h-11 items-center justify-center gap-1.5 rounded-[10px] border border-line px-4 text-[13.5px] font-semibold text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink-soft dark:border-transparent dark:bg-white/5 dark:text-ink-muted dark:disabled:hover:text-ink-muted"
          >
            <DownloadIcon size={14} />
            Dökümü İndir
          </button>
          <button
            onClick={resetSession}
            className="flex h-11 items-center justify-center gap-1.5 rounded-[10px] border border-line px-4 text-[13.5px] font-semibold text-ink-soft transition-colors hover:border-brand hover:text-brand dark:border-transparent dark:bg-white/5 dark:text-ink-muted"
          >
            <PlusIcon size={14} />
            Yeni Sohbet
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
        <div
          ref={scrollRef}
          className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-[22px] py-6"
        >
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
            <ChatBubble key={m.id} message={m} />
          ))}
          {/* "VİRA düşünüyor…" artık BURADA DEĞİL, yanıt balonunun içinde
              (bkz. ChatBubble). Beklenen yanıtın yerinde durması, ekranın
              başka bir köşesinde durmasından daha anlaşılır. */}
        </div>

        <div className="flex shrink-0 flex-wrap gap-2 px-[22px] pb-2">
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
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={sending}
            placeholder="Portföyün hakkında bir soru sor…"
            className="h-[46px] flex-1 rounded-[10px] border border-line px-4 text-sm outline-none transition-shadow focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] disabled:opacity-60 dark:border-transparent dark:bg-white/[0.06] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#C4485A] dark:focus:shadow-[0_0_0_3px_rgba(196,72,90,.2)]"
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
