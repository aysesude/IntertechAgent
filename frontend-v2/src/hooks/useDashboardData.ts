import { endpoints } from "@/api/endpoints";
import { mockDashboard } from "@/data/mockData";
import { useApiResource } from "./useApiResource";

export function useDashboardData() {
  return useApiResource(endpoints.getDashboard, mockDashboard);
}
