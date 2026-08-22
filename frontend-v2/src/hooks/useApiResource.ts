import { useEffect, useState, useCallback } from "react";
import { isApiConfigured } from "@/api/client";

export interface ApiResourceState<T> {
  data: T;
  loading: boolean;
  error: string | null;
  isLive: boolean;
  refetch: () => void;
}

/**
 * Bir API çağrısını mock veriye karşı çalıştırır: gerçek API taban adresi
 * (VITE_API_BASE_URL) tanımlıysa canlı veri denenir; tanımlı değilse veya
 * istek başarısız olursa bileşenler mock veriyle prop olarak beslenmeye
 * devam eder. Bileşenlerin kendisi hiçbir zaman fetch çağırmaz.
 */
export function useApiResource<T>(fetcher: () => Promise<T>, fallback: T): ApiResourceState<T> {
  const [data, setData] = useState<T>(fallback);
  const [loading, setLoading] = useState(isApiConfigured);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!isApiConfigured) {
      setData(fallback);
      setLoading(false);
      setIsLive(false);
      return;
    }

    setLoading(true);
    setError(null);
    fetcher()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setIsLive(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setData(fallback);
        setIsLive(false);
        setError(err instanceof Error ? err.message : "Bilinmeyen hata");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, isLive, refetch };
}
