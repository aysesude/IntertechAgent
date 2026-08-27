import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchMarketCalendar,
  fetchMarketHeadlines,
  fetchMarketIndicators,
  fetchPortfolioInfluence,
  type ApiMarketCalendarList,
  type ApiMarketHeadlineList,
  type ApiMarketIndicatorList,
  type ApiPortfolioInfluenceList,
} from "@/api/market";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";
import {
  toCalendarEvents,
  toInfluenceRows,
  toMarketIndicators,
  toNewsItems,
} from "@/adapters/market";
import { mockMarketPage } from "@/data/mockData";
import type { MarketPageData } from "@/types/finance";

export interface MarketState {
  data: MarketPageData;
  /** İlk yükleme — ekranda gösterilecek gerçek veri henüz yok. */
  loading: boolean;
  error: string | null;
  isDemoData: boolean;
  /** Gündem alınamadı ama şerit geldi: kısmi durum, ayrı uyarı. */
  headlinesError: string | null;
  refetch: () => void;
}

/**
 * KISMİ SONUÇ HATA DEĞİLDİR.
 *
 * Üç uç birbirinden bağımsız: gösterge şeridi veritabanından, gündem
 * BloombergHT'den canlı, etki listesi portföyden. Gündem düşerse şerit yine
 * gösterilir ve "gündeme ulaşılamadı" ayrıca söylenir — üçünü tek
 * `Promise.all`'a bağlamak, canlı bir dış kaynağın kesintisinde tüm ekranı
 * karartırdı (dashboard/portfolio hook'larındaki `.catch(() => null)`
 * yaklaşımının aynısı).
 */
interface TemelVeri {
  gostergeler: ApiMarketIndicatorList | null;
  gundem: ApiMarketHeadlineList | null;
  etki: ApiPortfolioInfluenceList | null;
  takvim: ApiMarketCalendarList | null;
}

/**
 * Modül düzeyinde önbellek — diğer sayfa hook'larıyla aynı gerekçe:
 * `AnimatePresence mode="wait"` sayfa değişiminde bileşeni unmount ediyor,
 * React state'i bunu hayatta tutamaz. `userId` eşleşmesi zorunlu (AK 5.4):
 * etki listesi kullanıcıya özel, başkasınınki bir an bile görünemez.
 */
let paylasilanOnbellek: { userId: string; temel: TemelVeri } | null = null;

/** Modül önbelleğini boşaltır. YALNIZCA TESTLER İÇİN. */
export function __marketOnbelleginiSifirla(): void {
  paylasilanOnbellek = null;
}

const BOS_MARKET: MarketPageData = {
  indicators: [],
  news: [],
  influence: [],
  calendar: [],
};

export function useMarketData(): MarketState {
  const userId = useCurrentUserId();
  const canli = isApiConfigured && userId !== null;

  const onbellekGecerli = paylasilanOnbellek?.userId === userId;
  const [temel, setTemel] = useState<TemelVeri | null>(
    onbellekGecerli ? paylasilanOnbellek!.temel : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [headlinesError, setHeadlinesError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const nesil = useRef(0);

  // Kullanıcı değişimi: önbellek başkasına aitse anında geçersiz (AK 5.4).
  useEffect(() => {
    if (paylasilanOnbellek?.userId === userId) return;
    nesil.current += 1;
    paylasilanOnbellek = null;
    setTemel(null);
  }, [userId]);

  useEffect(() => {
    if (!canli) return;
    const kullanici = userId!;
    const benimNesil = nesil.current;

    Promise.all([
      // Şerit zorunlu: düşerse ekranın omurgası yok demektir.
      fetchMarketIndicators(),
      // Gündem, etki ve takvim opsiyonel — biri düşerse diğerleri çizilir.
      fetchMarketHeadlines().catch(() => null),
      fetchPortfolioInfluence(kullanici).catch(() => null),
      fetchMarketCalendar(kullanici).catch(() => null),
    ])
      .then(([gostergeler, gundem, etki, takvim]) => {
        if (nesil.current !== benimNesil) return;
        const yeniTemel = { gostergeler, gundem, etki, takvim };
        setTemel(yeniTemel);
        paylasilanOnbellek = { userId: kullanici, temel: yeniTemel };
        setError(null);
        setHeadlinesError(gundem === null ? "Piyasa gündemine şu an ulaşılamıyor." : null);
      })
      .catch((err: unknown) => {
        if (nesil.current !== benimNesil) return;
        setTemel(null);
        setError(err instanceof Error ? err.message : "Piyasa verisi alınamadı.");
      });
  }, [canli, userId, tick]);

  const canliVeri = temel !== null;

  const data: MarketPageData = canliVeri
    ? {
        indicators: temel.gostergeler ? toMarketIndicators(temel.gostergeler) : [],
        news: temel.gundem ? toNewsItems(temel.gundem) : [],
        influence: temel.etki ? toInfluenceRows(temel.etki) : [],
        calendar: temel.takvim ? toCalendarEvents(temel.takvim) : [],
      }
    : canli
      ? BOS_MARKET
      : mockMarketPage;

  const refetch = useCallback(() => {
    nesil.current += 1;
    paylasilanOnbellek = null;
    setTick((t) => t + 1);
  }, []);

  return {
    data,
    loading: canli && !canliVeri,
    error,
    isDemoData: !canliVeri,
    headlinesError,
    refetch,
  };
}
