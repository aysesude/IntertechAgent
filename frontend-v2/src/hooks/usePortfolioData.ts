import { endpoints } from "@/api/endpoints";
import { mockPortfolioPage } from "@/data/mockData";
import { useApiResource } from "./useApiResource";

export function usePortfolioData() {
  return useApiResource(endpoints.getPortfolio, mockPortfolioPage);
}
