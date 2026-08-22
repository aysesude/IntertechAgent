import { endpoints } from "@/api/endpoints";
import { mockMarketPage } from "@/data/mockData";
import { useApiResource } from "./useApiResource";

export function useMarketData() {
  return useApiResource(endpoints.getMarket, mockMarketPage);
}
