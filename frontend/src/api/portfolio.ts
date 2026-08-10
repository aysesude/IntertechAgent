import { API_BASE_URL, extractErrorDetail } from "./client";
import type { PortfolioSummary } from "../types/portfolio";

export async function fetchPortfolioSummary(userId: string): Promise<PortfolioSummary> {
  const response = await fetch(`${API_BASE_URL}/api/portfolio/${userId}`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response));
  }
  return (await response.json()) as PortfolioSummary;
}
