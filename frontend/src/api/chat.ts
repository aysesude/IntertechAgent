import { API_BASE_URL, extractErrorDetail } from "./client";
import type {
  ChatDoneEvent,
  ChatErrorEvent,
  ChatRequest,
  ChatSessionEvent,
  ChatTokenEvent,
} from "../types/chat";

export interface ChatStreamHandlers {
  onSession?: (event: ChatSessionEvent) => void;
  onToken?: (event: ChatTokenEvent) => void;
  onDone?: (event: ChatDoneEvent) => void;
  onError?: (event: ChatErrorEvent) => void;
}

// Backend'in POST body ile SSE döndürmesi gerektiği için tarayıcının yerleşik
// EventSource'u (sadece GET destekler) kullanılamıyor; fetch + ReadableStream
// üzerinden `event:`/`data:` çerçevelerini elle ayrıştırıyoruz.
export async function streamChat(
  request: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(await extractErrorDetail(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette çerçeveleri CRLF (\r\n\r\n) ile ayırıyor; \n\n'e normalize et.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      dispatchFrame(buffer.slice(0, boundary), handlers);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function dispatchFrame(rawFrame: string, handlers: ChatStreamHandlers): void {
  let eventName = "message";
  let dataLine = "";
  for (const line of rawFrame.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLine = line.slice("data:".length).trim();
    }
  }
  if (!dataLine) return;

  const data: unknown = JSON.parse(dataLine);
  switch (eventName) {
    case "session":
      handlers.onSession?.(data as ChatSessionEvent);
      break;
    case "token":
      handlers.onToken?.(data as ChatTokenEvent);
      break;
    case "done":
      handlers.onDone?.(data as ChatDoneEvent);
      break;
    case "error":
      handlers.onError?.(data as ChatErrorEvent);
      break;
  }
}
