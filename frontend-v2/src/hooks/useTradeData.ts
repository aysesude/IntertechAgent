import { useCallback, useEffect, useState } from "react";
import { fetchTradableAssets, type ApiTradableList } from "@/api/trade";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";
import { __portfolioOnbelleginiSifirla } from "@/hooks/usePortfolioData";
import { __dashboardOnbelleginiSifirla } from "@/hooks/useDashboardData";

/**
 * Al/Sat ekranının verisi.
 *
 * Modül önbelleği YOK, bilerek — diğer ekranların aksine. Buradaki liste
 * nakit bakiyesini ve eldeki miktarları taşıyor, yani her işlemden sonra
 * eskiyor. Önbellekten okumak, kullanıcıya az önce harcadığı parayı hâlâ
 * duruyormuş gibi göstermek olurdu.
 */
export interface TradeState {
  data: ApiTradableList | null;
  loading: boolean;
  error: string | null;
  /** İşlemden sonra çağrılır: liste + portföy/dashboard önbellekleri. */
  refetch: () => void;
}

export function useTradeData(): TradeState {
  const userId = useCurrentUserId();
  const [data, setData] = useState<ApiTradableList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!isApiConfigured || !userId) {
      setLoading(false);
      return;
    }
    let iptal = false;
    setLoading(true);
    setError(null);

    fetchTradableAssets(userId)
      .then((sonuc) => {
        if (!iptal) setData(sonuc);
      })
      .catch((err: unknown) => {
        if (!iptal) setError(err instanceof Error ? err.message : "Varlık listesi alınamadı.");
      })
      .finally(() => {
        if (!iptal) setLoading(false);
      });

    return () => {
      iptal = true;
    };
  }, [userId, tick]);

  const refetch = useCallback(() => {
    // PORTFÖY VE DASHBOARD ÖNBELLEKLERİ DE BOŞALTILIR.
    //
    // İkisi de modül düzeyinde önbellek tutuyor (sayfa geçişinde unmount
    // oldukları için). İşlemden sonra boşaltılmazsa kullanıcı Al/Sat'tan
    // portföye döndüğünde az önce aldığı varlığı GÖRMEZ ve işlemin
    // çalışmadığını sanır — bu ekranın varlık sebebi tam da etkiyi
    // göstermek.
    __portfolioOnbelleginiSifirla();
    __dashboardOnbelleginiSifirla();
    setTick((t) => t + 1);
  }, []);

  return { data, loading, error, refetch };
}
