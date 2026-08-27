import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchRiskAssessment, type ApiRiskAssessment } from "@/api/risk";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { toRiskPageData } from "@/adapters/risk";
import { mockRiskPage } from "@/data/mockData";
import type { RiskPageData } from "@/types/finance";

export interface RiskState {
  data: RiskPageData;
  /** İlk yükleme — ekranda gösterilecek gerçek veri henüz yok. */
  loading: boolean;
  error: string | null;
  isDemoData: boolean;
  refetch: () => void;
}

/**
 * Modül düzeyinde önbellek — `usePortfolioData.ts`/`useDashboardData.ts`'teki
 * gerekçeyle birebir aynı: `AnimatePresence mode="wait"` sayfa değişiminde
 * Risk'i unmount ediyor, React state'i bunu hayatta tutamaz. `userId`
 * eşleşmesi zorunlu (AK 5.4) — başkasının verisi bir an bile gösterilemez.
 */
let paylasilanOnbellek: { userId: string; risk: ApiRiskAssessment } | null = null;

/** Modül önbelleğini boşaltır. YALNIZCA TESTLER İÇİN. */
export function __riskOnbelleginiSifirla(): void {
  paylasilanOnbellek = null;
}

const BOS_RISK: RiskPageData = {
  overview: { profileLabel: "", levelLabel: null, level: null, isWithinProfile: null, verdict: "" },
  contributions: [],
  diversification: { herfindahlIndex: 0, diversificationRatio: null, maxClassWeightPct: 0, maxClassLabel: null },
  assets: [],
  valueAtRisk: { amount: null, formattedAmount: "—", confidencePct: 0, horizonLabel: "" },
  sharpe: { value: null, note: "" },
  warnings: [],
};

export function useRiskData(): RiskState {
  const userId = useCurrentUserId();
  const { resolvedTheme } = useTheme();
  const canli = isApiConfigured && userId !== null;

  const onbellekGecerli = paylasilanOnbellek?.userId === userId;
  const [risk, setRisk] = useState<ApiRiskAssessment | null>(
    onbellekGecerli ? paylasilanOnbellek!.risk : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const nesil = useRef(0);

  // Kullanıcı değişimi: önbellek başkasına aitse anında geçersiz (AK 5.4).
  useEffect(() => {
    if (paylasilanOnbellek?.userId === userId) return;
    nesil.current += 1;
    paylasilanOnbellek = null;
    setRisk(null);
  }, [userId]);

  useEffect(() => {
    if (!canli) return;
    const kullanici = userId!;
    const benimNesil = nesil.current;

    fetchRiskAssessment(kullanici)
      .then((sonuc) => {
        if (nesil.current !== benimNesil) return;
        setRisk(sonuc);
        paylasilanOnbellek = { userId: kullanici, risk: sonuc };
        setError(null);
      })
      .catch((err: unknown) => {
        if (nesil.current !== benimNesil) return;
        setRisk(null);
        setError(err instanceof Error ? err.message : "Risk verisi alınamadı.");
      });
  }, [canli, userId, tick]);

  const canliVeri = risk !== null;

  // Sınıf renkleri temaya bağlı (bkz. adapters/risk.ts:toContributions) —
  // tema değişimi yeniden fetch GEREKTİRMEMELİ, sadece yeniden türetmeli.
  const data = useMemo<RiskPageData>(() => {
    if (canliVeri) return toRiskPageData(risk, resolvedTheme === "dark");
    return canli ? BOS_RISK : mockRiskPage;
  }, [risk, canliVeri, canli, resolvedTheme]);

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
