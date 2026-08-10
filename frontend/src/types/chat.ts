import type { PortfolioSummary } from "./portfolio";

export type MessageRole = "user" | "assistant";
export type MessageStatus = "complete" | "incomplete";

export interface MessageOut {
  id: string;
  role: MessageRole;
  content: string;
  agent_name: string | null;
  meta: Record<string, unknown> | null;
  status: MessageStatus;
  created_at: string;
}

export interface ChatRequest {
  user_id: string;
  session_id: string | null;
  message: string;
}

export interface ChatSessionEvent {
  session_id: string;
}

export interface ChatTokenEvent {
  delta: string;
}

export interface ChatDoneEvent {
  agent: string | null;
  final_answer: string;
  data: PortfolioSummary | null;
}

export interface ChatErrorEvent {
  message: string;
}
