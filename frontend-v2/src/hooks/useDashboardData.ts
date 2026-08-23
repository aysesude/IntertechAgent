import { useCallback, useEffect, useState } from "react";
import {
  fetchHoldings,
  fetchPerformance,
  fetchPortfolioSummary,
  fetchTransactions,
  type ApiPortfolioSummary,
} from "@/api/portfolio";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import {
  WINDOW_BY_RANGE,
  priceFreshnessWarning,
  toDashboardData,
} from "@/adapters/dashboard";
import { mockDashboard } from "@/data/mockData";
import type { DashboardData, RangeKey } from "@/types/finance";

export interface DashboardState {
  data: DashboardData;
  loading: boolean;
  error: string | null;
  isDemoData: boolean;
  /** Fiyatların bir kısmı eskiyse gösterilecek uyarı (AK 5.3 / docs/API.md). */
  freshnessWarning: string | null;
  refetch: () => void;
}

/**
 * Dashboard verisi.
 *
 * DÖRT UÇTAN besleniyor ve ikisi ZORUNLU, ikisi opsiyonel:
 * - `summary` + `performance` olmadan ekran çizilemez → hata gösterilir.
 * - `holdings` + `transactions` düşerse ekran yine çizilir; yalnızca donut'un
 *   alt kırılımı ve son işlemler listesi boş kalır. Kısmi başarısızlıkta
 *   her şeyi karartmak, elde olan veriyi de saklamak olurdu.
 *
 * `range` değişince yalnızca performans yeniden çekilir — özet ve varlıklar
 * dönemden bağımsız.
 */
export function useDashboardData(range: RangeKey): DashboardState {
  const userId = useCurrentUserId();
  const { resolvedTheme } = useTheme();
  const canli = isApiConfigured && userId !== null;

  const [data, setData] = useState<DashboardData>(mockDashboard);
  const [loading, setLoading] = useState(canli);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [freshnessWarning, setFreshnessWarning] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!canli) {
      setData(mockDashboard);
      setLoading(false);
      setIsLive(false);
      return;
    }

    let iptal = false;
    setLoading(true);
    setError(null);

    async function yukle(kullanici: string) {
      // Zorunlu ikisi paralel: ekranın iskeleti bunlara bağlı.
      const [ozet, performans] = await Promise.all([
        fetchPortfolioSummary(kullanici),
        fetchPerformance(kullanici, WINDOW_BY_RANGE[range]),
      ]);
      // Opsiyonel ikisi: hata verirlerse `null` ile devam edilir.
      const [varliklar, islemler] = await Promise.all([
        fetchHoldings(kullanici).catch(() => null),
        fetchTransactions(kullanici).catch(() => null),
      ]);
      return { ozet, performans, varliklar, islemler };
    }

    yukle(userId!)
      .then(({ ozet, performans, varliklar, islemler }) => {
        if (iptal) return;
        setData(
          toDashboardData({
            summary: ozet,
            performance: performans,
            range,
            holdings: varliklar,
            transactions: islemler,
            darkTheme: resolvedTheme === "dark",
          }),
        );
        setFreshnessWarning(priceFreshnessWarning(ozet as ApiPortfolioSummary));
        setIsLive(true);
      })
      .catch((err: unknown) => {
        if (iptal) return;
        setIsLive(false);
        setError(err instanceof Error ? err.message : "Portföy verisi alınamadı.");
      })
      .finally(() => {
        if (!iptal) setLoading(false);
      });

    return () => {
      iptal = true;
    };
  }, [canli, userId, range, resolvedTheme, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, isDemoData: !isLive, freshnessWarning, refetch };
}
