import { useEffect, useRef, useState } from "react";
import { fetchBenchmark, type ApiBenchmarkComparison, type ApiWindow } from "@/api/portfolio";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";

/**
 * "Varlıklar Arası Karşılaştırmalı Getiri" kartının verisi.
 *
 * `useApiResource` KULLANILMIYOR, bilerek: o kanca yalnızca `refetch`
 * çağrılınca yeniden yüklüyor, `fetcher` değişince değil (kendi yorumunda
 * yazıyor — kapanış her render'da yenilendiği için bağımlılığa konulamıyor).
 * Buradaysa dönem düğmesi her basıldığında YENİ bir pencere isteniyor;
 * o kancayla dönem değişimi hiç istek atmazdı.
 *
 * Dönem değişirken ÖNCEKİ veri ekranda tutuluyor. `null`'a düşseydi grafik
 * DOM'dan kalkar, kart yüksekliği sıfırlanır, sayfa zıplar ve veri gelince
 * yeniden belirirdi — `useDashboardData` aynı sorunu aynı gerekçeyle
 * çözüyor.
 */
export interface BenchmarkState {
  data: ApiBenchmarkComparison | null;
  /** İlk yükleme: gösterilecek hiçbir veri yok. */
  loading: boolean;
  /** Yalnızca dönem değişiyor; eldeki seri geçerli kalır. */
  periodLoading: boolean;
  error: string | null;
}

export function useBenchmarkData(window: ApiWindow): BenchmarkState {
  const userId = useCurrentUserId();
  const [data, setData] = useState<ApiBenchmarkComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Elde veri var mı — `data` state'i efekt içinde okunsaydı bağımlılığa
  // girmesi ve her yüklemede efekti yeniden tetiklemesi gerekirdi.
  const veriVar = useRef(false);

  useEffect(() => {
    if (!isApiConfigured || !userId) {
      setLoading(false);
      return;
    }

    let iptal = false;
    if (veriVar.current) setPeriodLoading(true);
    else setLoading(true);
    setError(null);

    fetchBenchmark(userId, window)
      .then((sonuc) => {
        if (iptal) return;
        setData(sonuc);
        veriVar.current = true;
      })
      .catch((err: unknown) => {
        if (iptal) return;
        // Veri SIFIRLANMIYOR: eldeki seri eski dönemin ama gerçek. Onu
        // silip boş kart göstermek, hatayı da gizleyip kullanıcıyı veri
        // yokmuş sanısına düşürürdü. Hata mesajı ayrıca gösteriliyor.
        setError(err instanceof Error ? err.message : "Kıyaslama verisi alınamadı.");
      })
      .finally(() => {
        if (iptal) return;
        setLoading(false);
        setPeriodLoading(false);
      });

    return () => {
      iptal = true;
    };
  }, [userId, window]);

  return { data, loading, periodLoading, error };
}
