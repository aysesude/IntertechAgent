import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchHoldings,
  fetchPortfolioSummary,
  type ApiHoldingsValuation,
  type ApiPortfolioSummary,
} from "@/api/portfolio";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";
import { toPortfolioPageData } from "@/adapters/portfolio";
import { mockPortfolioPage } from "@/data/mockData";
import type { PortfolioPageData } from "@/types/finance";

export interface PortfolioState {
  data: PortfolioPageData;
  /** İlk yükleme — ekranda gösterilecek gerçek veri henüz yok. */
  loading: boolean;
  error: string | null;
  isDemoData: boolean;
  refetch: () => void;
}

/** Dönem seçici YOK (Dashboard'ın aksine) — tek fetch döngüsü yeterli. */
interface TemelVeri {
  ozet: ApiPortfolioSummary;
  /** `/holdings` düşerse `null`; kart/tablo veri yokken de çizilir. */
  holdings: ApiHoldingsValuation | null;
}

/**
 * Modül düzeyinde önbellek — `useDashboardData.ts`'teki gerekçeyle birebir
 * aynı: `AnimatePresence mode="wait"` sayfa değişiminde Portfolio'yu
 * unmount ediyor, React state'i bunu hayatta tutamaz. `userId` eşleşmesi
 * zorunlu (AK 5.4) — başkasının verisi bir an bile gösterilemez.
 */
let paylasilanOnbellek: { userId: string; temel: TemelVeri } | null = null;

/** Modül önbelleğini boşaltır. YALNIZCA TESTLER İÇİN. */
export function __portfolioOnbelleginiSifirla(): void {
  paylasilanOnbellek = null;
}

const BOS_PORTFOLIO: PortfolioPageData = {
  assetClasses: [],
  holdings: [],
  riskSummary: [],
  instrumentCount: 0,
  assetClassCount: 0,
};

export function usePortfolioData(): PortfolioState {
  const userId = useCurrentUserId();
  const canli = isApiConfigured && userId !== null;

  const onbellekGecerli = paylasilanOnbellek?.userId === userId;
  const [temel, setTemel] = useState<TemelVeri | null>(
    onbellekGecerli ? paylasilanOnbellek!.temel : null,
  );
  const [error, setError] = useState<string | null>(null);
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
      fetchPortfolioSummary(kullanici),
      // Opsiyonel: düşerse `null` ile devam edilir, kartlar/tablo boş
      // kırılımla çizilir (dashboard.ts'teki holdings ile aynı yaklaşım).
      fetchHoldings(kullanici).catch(() => null),
    ])
      .then(([ozet, holdings]) => {
        if (nesil.current !== benimNesil) return;
        const yeniTemel = { ozet, holdings };
        setTemel(yeniTemel);
        paylasilanOnbellek = { userId: kullanici, temel: yeniTemel };
        setError(null);
      })
      .catch((err: unknown) => {
        if (nesil.current !== benimNesil) return;
        setTemel(null);
        setError(err instanceof Error ? err.message : "Portföy verisi alınamadı.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canli, userId, tick]);

  const canliVeri = temel !== null;

  const data: PortfolioPageData = canliVeri
    ? toPortfolioPageData({ summary: temel.ozet, holdings: temel.holdings })
    : canli
      ? BOS_PORTFOLIO
      : mockPortfolioPage;

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
    refetch,
  };
}
