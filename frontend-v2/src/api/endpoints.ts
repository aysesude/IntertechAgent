import { apiGet, apiPost } from "./client";
import type {
  ChatMessage,
  ChatPageData,
  DashboardData,
  MarketPageData,
  PortfolioPageData,
  RiskPageData,
} from "@/types/finance";

/**
 * Gerçek backend uçları. VITE_API_BASE_URL tanımlandığında bu fonksiyonlar
 * canlı sunucuya istek atar; sunucu yoksa veya istek başarısız olursa
 * çağıran hook'lar mock veriye düşer (bkz. src/hooks).
 */
export const endpoints = {
  getDashboard: () => apiGet<DashboardData>("/dashboard"),
  getPortfolio: () => apiGet<PortfolioPageData>("/portfolio"),
  getMarket: () => apiGet<MarketPageData>("/market"),
  getRisk: () => apiGet<RiskPageData>("/risk"),
  getChat: () => apiGet<ChatPageData>("/chat"),
  postChatMessage: (text: string) => apiPost<ChatMessage>("/chat/messages", { text }),
};
