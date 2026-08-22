import { useCallback, useEffect, useState } from "react";
import { isApiConfigured } from "@/api/client";

export interface ApiResourceState<T> {
  data: T;
  loading: boolean;
  error: string | null;
  /** Veri gerçekten sunucudan geldi. */
  isLive: boolean;
  /**
   * Gösterilen veri TASARIM VERİSİ, sunucudan gelmedi. Ekran bunu görünür
   * kılmalı — bir finans ürününde uydurma rakamı gerçekmiş gibi göstermek
   * kabul edilebilir bir hata modu değil (CLAUDE.md §4).
   */
  isDemoData: boolean;
  refetch: () => void;
}

/**
 * Bir ekranın verisini yükler.
 *
 * `fetcher === null` → ekran henüz backend'e bağlanmadı; istek ATILMAZ, mock
 * veri `isDemoData: true` ile döner. Var olmayan bir uca boşa istek atıp 404
 * yiyerek mock'a "düşmek" ile bilerek tasarım verisi göstermek aynı şey değil;
 * ikincisi bilinçli bir durum ve öyle işaretleniyor.
 *
 * `fetcher` verilmişse istek atılır. HATA DURUMUNDA veri yine mock'a döner ama
 * `error` DOLU ve `isDemoData` TRUE olur — **bağlanmış bir ekran `error`ı
 * göstermek zorundadır**, aksi halde backend düştüğünde kullanıcı uydurma
 * rakamları gerçek sanır. Bu, taşınan koddaki en tehlikeli davranıştı:
 * hata sessizce yutuluyor, ekran hiçbir şey olmamış gibi mock gösteriyordu.
 */
export function useApiResource<T>(
  fetcher: (() => Promise<T>) | null,
  fallback: T,
): ApiResourceState<T> {
  const shouldFetch = fetcher !== null && isApiConfigured;

  const [data, setData] = useState<T>(fallback);
  const [loading, setLoading] = useState(shouldFetch);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    if (!shouldFetch) {
      setData(fallback);
      setLoading(false);
      setIsLive(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    fetcher!()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setIsLive(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setData(fallback);
        setIsLive(false);
        setError(err instanceof Error ? err.message : "Veri alınamadı.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // fetcher her render'da yeniden oluşan bir kapanış (closure) olabilir;
    // bağımlılığa koymak sonsuz döngü üretir. Yeniden yükleme `refetch`
    // (tick) üzerinden, bilinçli olarak tetiklenir.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, shouldFetch]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, isLive, isDemoData: !isLive, refetch };
}
