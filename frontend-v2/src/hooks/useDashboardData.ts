import { mockDashboard } from "@/data/mockData";
import { useApiResource } from "./useApiResource";

export function useDashboardData() {
  // Bu ekran henüz backend'e bağlanmadı: `null` fetcher ile istek ATILMAZ ve
  // veri `isDemoData: true` olarak işaretlenir (bkz. useApiResource).
  // Bağlanınca burası `() => fetchX(userId)` olacak ve dönüşüm
  // `src/adapters/` altında yapılacak.
  return useApiResource(null, mockDashboard);
}
