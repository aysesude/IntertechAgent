import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { streamChat } from "@/api/chat";
import { useCurrentUserId } from "@/auth/AuthContext";
import type { ChatMessage } from "@/types/finance";

/**
 * Sohbet oturumu.
 *
 * NEDEN CONTEXT: aynı konuşma iki yerden görünüyor — AI Chat sayfası ve her
 * sayfada duran yüzen widget. Durum bileşenlerin içinde tutulsaydı widget'ta
 * başlanan konuşma sayfaya geçince kaybolurdu; ajan da önceki mesajları
 * bağlam olarak göremezdi (backend son N mesajı Orchestrator'a geçiriyor).
 *
 * `session_id` ilk mesajda sunucudan `event: session` ile gelir ve sonraki
 * isteklerde geri gönderilir. Sağlayıcı yalnızca giriş yapılmış ağacın
 * içinde mount edildiği için çıkışta durum kendiliğinden sıfırlanır.
 */

interface ChatContextValue {
  messages: ChatMessage[];
  /** Bir cevap bekleniyor (istek gitti, `done` gelmedi). */
  sending: boolean;
  sendMessage: (text: string) => Promise<void>;
  /** Yeni sohbet: mesajlar ve oturum kimliği sıfırlanır. */
  resetSession: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

function saatDamgasi(): string {
  return new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const userId = useCurrentUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Sağlayıcı sökülürken (çıkış, sayfa kapanışı) açık akış bırakılmaz.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  /** Son asistan mesajını günceller. Akış boyunca tek değişen kayıt odur. */
  const sonAsistani = useCallback((guncelle: (mesaj: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      const son = prev[prev.length - 1];
      if (!son || son.role !== "assistant") return prev;
      return [...prev.slice(0, -1), guncelle(son)];
    });
  }, []);

  const resetSession = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    sessionIdRef.current = null;
    setMessages([]);
    setSending(false);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const mesaj = text.trim();
      if (!mesaj || sending) return;
      if (!userId) return; // giriş yapılmadan sohbet edilemez

      const zaman = saatDamgasi();
      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", text: mesaj, createdAt: zaman },
        { id: `a-${Date.now()}`, role: "assistant", text: "", createdAt: zaman, streaming: true },
      ]);
      setSending(true);

      const controller = new AbortController();
      abortRef.current = controller;

      let tamamlandi = false;
      try {
        await streamChat(
          { user_id: userId, session_id: sessionIdRef.current, message: mesaj },
          {
            onSession: ({ session_id }) => {
              sessionIdRef.current = session_id;
            },
            onToken: ({ delta }) => {
              sonAsistani((m) => ({ ...m, text: m.text + delta }));
            },
            onDone: ({ agent, final_answer }) => {
              tamamlandi = true;
              sonAsistani((m) => ({
                ...m,
                // AJAN HATA VERDİĞİNDE HİÇ `token` OLAYI GELMİYOR (ör. RAG
                // sonuç bulamadı): cevap yalnızca `final_answer`'da oluyor.
                // İçerik doluysa dokunmuyoruz — normal akışta metin zaten
                // token token birikti ve `final_answer` ile aynı.
                text: m.text || final_answer,
                agentName: agent,
                streaming: false,
              }));
            },
            onError: ({ message }) => {
              tamamlandi = true;
              sonAsistani((m) => ({
                ...m,
                text: m.text || "",
                error: message,
                streaming: false,
              }));
            },
          },
          controller.signal,
        );
      } catch (error) {
        // İptal kullanıcı eylemidir (yeni sohbet, sayfadan ayrılma), hata değil.
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        sonAsistani((m) => ({
          ...m,
          error: error instanceof Error ? error.message : "Yanıt alınamadı.",
          streaming: false,
        }));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        // Akış `done` gelmeden bittiyse cevap eksiktir; sunucu da bu durumu
        // `status: incomplete` ile kaydediyor (bkz. backend/app/api/chat.py).
        if (!tamamlandi) {
          sonAsistani((m) =>
            m.streaming ? { ...m, streaming: false, incomplete: m.text.length > 0 } : m,
          );
        }
        setSending(false);
      }
    },
    [userId, sending, sonAsistani],
  );

  const value = useMemo<ChatContextValue>(
    () => ({ messages, sending, sendMessage, resetSession }),
    [messages, sending, sendMessage, resetSession],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextValue {
  const context = useContext(ChatContext);
  if (context === null) {
    throw new Error("useChat, ChatProvider içinde çağrılmalı.");
  }
  return context;
}
