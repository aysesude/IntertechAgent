import { useCallback, useEffect, useState } from "react";
import { isApiConfigured } from "@/api/client";
import { fetchInsightCards, type ApiInsightCard } from "@/api/insight";
import { useCurrentUserId } from "@/auth/AuthContext";

/**
 * "Hızlı Özet" kartlarını yükler.
 *
 * ÖNBELLEK YOK — bilerek. Diğer ekran hook'larında modül düzeyi bir önbellek
 * var (bkz. `useRiskData`) çünkü sayfa geçişlerinde bileşen unmount oluyor ve
 * aynı veriyi yeniden çekmek gereksiz. Burada durum farklı: panel her
 * açılışta YENİDEN üretiliyor (ürün kararı) — açmak yenilemek demek.
 *
 * MOCK'A DÜŞMÜYOR. Diğer ekranlar API bağlı değilken tasarım verisi
 * gösteriyor; bu panelin tasarım verisi YOK ve olmamalı: uydurma bir "özet"
 * göstermek, kartların taşıdığı tek değeri (ölçülmüş veriye dayanmak) yok
 * ederdi. API bağlı değilse ya da istek düşerse `error` dolu, `cards` boş
 * döner ve panel bunu söyler.
 */
export interface InsightState {
  cards: ApiInsightCard[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const HATA_METNI = "Özet şu anda alınamadı. Lütfen tekrar deneyin.";

export function useInsightData(enabled: boolean): InsightState {
  const userId = useCurrentUserId();
  const [cards, setCards] = useState<ApiInsightCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    // `enabled` panelin açık olup olmadığı: kapalıyken istek ATILMAZ.
    // Sayfa açılışında otomatik üretim, her sayfa geçişine bir LLM turu
    // eklerdi (≤5 sn hedefi, bkz. A5 varsayımı).
    if (!enabled || !userId || !isApiConfigured) {
      return;
    }

    let iptal = false;
    setLoading(true);
    setError(null);

    fetchInsightCards(userId)
      .then((sonuc) => {
        if (iptal) return;
        setCards(sonuc.cards);
      })
      .catch(() => {
        if (iptal) return;
        setCards([]);
        setError(HATA_METNI);
      })
      .finally(() => {
        if (!iptal) setLoading(false);
      });

    return () => {
      iptal = true;
    };
  }, [enabled, userId, tick]);

  // Panel kapanınca kartlar temizlenir: bir sonraki açılışta ESKİ özet bir an
  // görünmemeli — üstünde tarih yazmayan eski bir metin, güncel sanılır.
  useEffect(() => {
    if (!enabled) {
      setCards([]);
      setError(null);
    }
  }, [enabled]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { cards, loading, error, refetch };
}
