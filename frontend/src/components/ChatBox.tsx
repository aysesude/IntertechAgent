import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api/chat";
import type { MessageRole } from "../types/chat";

interface DisplayMessage {
  role: MessageRole;
  content: string;
  streaming: boolean;
}

interface ChatBoxProps {
  userId: string;
}

function ChatBox({ userId }: ChatBoxProps): JSX.Element {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function updateLastAssistantMessage(update: (msg: DisplayMessage) => DisplayMessage): void {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      return [...prev.slice(0, -1), update(last)];
    });
  }

  async function handleSend(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    const text = input.trim();
    if (!text || isStreaming || !userId) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, streaming: false },
      { role: "assistant", content: "", streaming: true },
    ]);
    setInput("");
    setIsStreaming(true);

    try {
      await streamChat(
        { user_id: userId, session_id: sessionIdRef.current, message: text },
        {
          onSession: (event) => {
            sessionIdRef.current = event.session_id;
          },
          onToken: (event) => {
            updateLastAssistantMessage((msg) => ({ ...msg, content: msg.content + event.delta }));
          },
          onDone: () => {
            updateLastAssistantMessage((msg) => ({ ...msg, streaming: false }));
          },
          onError: (event) => {
            updateLastAssistantMessage((msg) => ({
              ...msg,
              content: msg.content || `Hata: ${event.message}`,
              streaming: false,
            }));
          },
        },
      );
    } catch (err) {
      updateLastAssistantMessage((msg) => ({
        ...msg,
        content: msg.content || `Hata: ${(err as Error).message}`,
        streaming: false,
      }));
    } finally {
      setIsStreaming(false);
    }
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="mb-2 flex-1 space-y-2 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <p className="text-sm text-gray-400">Portföyünüz hakkında bir soru sorun.</p>
        )}
        {messages.map((message, index) => (
          <div
            key={index}
            className={`max-w-[85%] rounded px-3 py-2 text-sm ${
              message.role === "user" ? "ml-auto bg-blue-50" : "bg-gray-100"
            }`}
          >
            {message.content}
            {message.streaming && <span className="animate-pulse">▍</span>}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSend} className="flex gap-2">
        <input
          className="flex-1 rounded border px-3 py-1.5 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Mesajınızı yazın..."
          disabled={isStreaming || !userId}
        />
        <button
          type="submit"
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={isStreaming || !input.trim() || !userId}
        >
          Gönder
        </button>
      </form>
    </div>
  );
}

export default ChatBox;
