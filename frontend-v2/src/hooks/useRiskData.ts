import { endpoints } from "@/api/endpoints";
import { mockRiskPage } from "@/data/mockData";
import { useApiResource } from "./useApiResource";

export function useRiskData() {
  return useApiResource(endpoints.getRisk, mockRiskPage);
}
