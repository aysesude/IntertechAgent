import { useCallback, useEffect, useRef, useState } from "react";
import { buildAssistantReply, mockChatPage } from "@/data/mockData";
import type { ChatMessage } from "@/types/finance";
import { useApiResource } from "./useApiResource";

export function useChatData() {
  // Faz 3'te SSE'ye bağlanacak: backend sohbeti `POST /api/chat` üzerinden
  // AKITARAK (streaming) döndürüyor, tek parça bir mesaj olarak değil.
  // O yüzden burada tek bir `fetch` yerine `frontend/src/api/chat.ts`'teki
  // çözülmüş SSE okuyucusu taşınacak.
  const resource = useApiResource(null, mockChatPage);
  const [messages, setMessages] = useState<ChatMessage[]>(resource.data.messages);
  const [sending, setSending] = useState(false);
  const syncedLiveData = useRef(false);

  useEffect(() => {
    if (resource.isLive && !syncedLiveData.current) {
      syncedLiveData.current = true;
      setMessages(resource.data.messages);
    }
  }, [resource.isLive, resource.data]);

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: trimmed,
      createdAt: new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMessage]);
    setSending(true);

    try {
      // Faz 3'e kadar tasarım yanıtı. Gerçek akış bağlandığında burası
      // streamChat(...) çağrısıyla değişecek.
      const reply = await simulateReply(trimmed);
      setMessages((prev) => [...prev, reply]);
    } finally {
      setSending(false);
    }
  }, []);

  return { ...resource, messages, sending, sendMessage };
}

function simulateReply(text: string): Promise<ChatMessage> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(buildAssistantReply(text)), 1200);
  });
}
