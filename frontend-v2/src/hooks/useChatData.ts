import { useCallback, useEffect, useRef, useState } from "react";
import { endpoints } from "@/api/endpoints";
import { isApiConfigured } from "@/api/client";
import { buildAssistantReply, mockChatPage } from "@/data/mockData";
import type { ChatMessage } from "@/types/finance";
import { useApiResource } from "./useApiResource";

export function useChatData() {
  const resource = useApiResource(endpoints.getChat, mockChatPage);
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
      const reply = isApiConfigured ? await endpoints.postChatMessage(trimmed) : await simulateReply(trimmed);
      setMessages((prev) => [...prev, reply]);
    } catch {
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
