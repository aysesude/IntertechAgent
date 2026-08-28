import { useCallback, useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/finance";

/**
 * Kullanıcı yeni bir mesaj gönderdiğinde, o mesajı akışın EN ÜSTÜNE hizalar
 * — konuşmanın en altına kaydırmak yerine. Asistanın yanıtı sorunun
 * ALTINDAKİ boş alanda akar; ekran her token geldiğinde aşağı zıplamaz,
 * kullanıcı az önce sorduğu soruyu gözden kaybetmez.
 *
 * Yalnızca YENİ bir kullanıcı mesajı eklendiğinde tetiklenir (id
 * karşılaştırmasıyla) — akış sırasında asistan metni güncellendikçe
 * TEKRAR kaydırma yapılmaz: kaydırma konumu kullanıcı mesajı üstte kalacak
 * şekilde sabitlendiğinde, altına eklenen içerik `scrollTop`'u etkilemez.
 *
 * Hem tam sayfa (ChatPage) hem ufak widget (ChatWidget) aynı davranışı
 * paylaşıyor, bu yüzden ortak bir hook.
 */
export function useScrollNewUserMessageToTop(messages: ChatMessage[]) {
  const bubbleRefs = useRef(new Map<string, HTMLDivElement>());
  const lastScrolledIdRef = useRef<string | null>(null);

  useEffect(() => {
    const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUserMessage || lastUserMessage.id === lastScrolledIdRef.current) return;
    lastScrolledIdRef.current = lastUserMessage.id;
    bubbleRefs.current.get(lastUserMessage.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [messages]);

  return useCallback((message: ChatMessage) => {
    if (message.role !== "user") return undefined;
    return (el: HTMLDivElement | null) => {
      if (el) bubbleRefs.current.set(message.id, el);
      else bubbleRefs.current.delete(message.id);
    };
  }, []);
}
