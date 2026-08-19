import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat } from "../api/chat";
import type { MessageRole } from "../types/chat";

// Asistan cevapları (RAG dokümanlarından gelen) markdown başlık/tablo
// içeriyor; ReactMarkdown olmadan "| Gösterge | 2026 Ç2 |" gibi ham
// sözdizimi ekrana aynen basılıyordu. remarkGfm, tablo (GFM) desteği için
// gerekli — temel react-markdown bunu kapsamaz.
const MARKDOWN_COMPONENTS = {
  table: (props: React.ComponentPropsWithoutRef<"table">) => (
    <table className="my-1 w-full border-collapse text-xs" {...props} />
  ),
  th: (props: React.ComponentPropsWithoutRef<"th">) => (
    <th className="border border-gray-300 bg-gray-50 px-2 py-1 text-left" {...props} />
  ),
  td: (props: React.ComponentPropsWithoutRef<"td">) => (
    <td className="border border-gray-300 px-2 py-1" {...props} />
  ),
  p: (props: React.ComponentPropsWithoutRef<"p">) => <p className="mb-1.5 last:mb-0" {...props} />,
  ul: (props: React.ComponentPropsWithoutRef<"ul">) => (
    <ul className="mb-1.5 list-disc pl-4" {...props} />
  ),
  h1: (props: React.ComponentPropsWithoutRef<"h1">) => (
    <h1 className="mb-1 mt-1 text-base font-semibold first:mt-0" {...props} />
  ),
  h2: (props: React.ComponentPropsWithoutRef<"h2">) => (
    <h2 className="mb-1 mt-2 text-sm font-semibold first:mt-0" {...props} />
  ),
};

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
          onDone: (event) => {
            // Ajan basarisiz oldugunda (ör. RAG NOT_FOUND, PROVIDER_UNAVAILABLE)
            // agent.execute() on_token'i hic cagirmiyor - "token" olayi hic
            // gelmiyor, mesaj bos kaliyor. Boyle durumlarda hata/bulunamadi
            // metni yalnizca final_answer'da geliyor; icerik zaten doluysa
            // (normal akis streaming'le doldurdu) buraya dokunmuyoruz.
            updateLastAssistantMessage((msg) => ({
              ...msg,
              content: msg.content || event.final_answer,
              streaming: false,
            }));
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
            {message.role === "assistant" ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                {message.content}
              </ReactMarkdown>
            ) : (
              message.content
            )}
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
