import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchHoldings,
  fetchPerformance,
  fetchPortfolioSummary,
  fetchTransactions,
  type ApiHoldingsValuation,
  type ApiPerformanceResult,
  type ApiPortfolioSummary,
  type ApiTransactionList,
} from "@/api/portfolio";
import { fetchRiskAssessment, type ApiRiskAssessment } from "@/api/risk";
import { isApiConfigured } from "@/api/client";
import { useCurrentUserId } from "@/auth/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { WINDOW_BY_RANGE, priceFreshnessWarning, toDashboardData } from "@/adapters/dashboard";
import { mockDashboard } from "@/data/mockData";
import type { DashboardData, PerformanceRange, RangeKey } from "@/types/finance";

export interface DashboardState {
  data: DashboardData;
  /** İlk yükleme — ekranda gösterilecek gerçek veri henüz yok. */
  loading: boolean;
  /** Yalnızca dönem değişiyor; ekranın geri kalanı geçerli kalır. */
  rangeLoading: boolean;
  error: string | null;
  isDemoData: boolean;
  /** Fiyatların bir kısmı eskiyse gösterilecek uyarı (AK 5.3 / docs/API.md). */
  freshnessWarning: string | null;
  /**
   * Grafikte GÖSTERİLECEK seri.
   *
   * İstenen dönem henüz yüklenmediyse bir ÖNCEKİ dönemin serisi döner.
   * `null` dönseydi grafik kartı DOM'dan kalkar, sayfa düzeni çöker ve veri
   * gelince kart yeniden belirirdi.
   */
  chartRange: PerformanceRange | null;
  refetch: () => void;
}

/** Dönemden BAĞIMSIZ veriler: dönem değişince yeniden çekilmezler. */
interface TemelVeri {
  ozet: ApiPortfolioSummary;
  varliklar: ApiHoldingsValuation | null;
  islemler: ApiTransactionList | null;
  /** Risk ucu düşerse `null`; kart "hesaplanamadı" gösterir, ekran çizilir. */
  risk: ApiRiskAssessment | null;
}

/**
 * Dashboard verisi.
 *
 * İKİ AYRI YÜKLEME var ve bu bilinçli:
 *
 * - **Temel** (`/portfolio`, `/holdings`, `/transactions`) dönemden bağımsız;
 *   yalnızca kullanıcı değişince ya da elle yenilenince çekilir.
 * - **Performans** (`/performance?window=`) döneme bağlı; dönem değişince TEK
 *   istek gider ve sonuç önbelleğe alınır — aynı döneme dönmek ağa çıkmaz.
 *
 * Tek effect'te toplansaydı dönem düğmesine her basışta dört uç birden
 * çekilirdi; dahası tema değişimi bile ağ isteği tetiklerdi (renk paleti
 * dönüşümün girdisi). Şimdi tema değişimi yalnızca yeniden türetir.
 *
 * NEDEN "NESİL" SAYACI, effect'e özgü `iptal` BAYRAĞI DEĞİL: `iptal`, effect
 * HERHANGİ bir sebeple yeniden çalıştığında uçuştaki isteğin cevabını da çöpe
 * atıyor. Ölçüldü — önbellek state'i bağımlılıktayken, sıfırlama effect'i onu
 * değiştirdiği an dönem effect'i yeniden çalışıyor, temizlik `iptal = true`
 * yapıyor ve tek isteğin cevabı sessizce yok sayılıyordu: grafik hiç gelmiyor,
 * `rangeLoading` sonsuza dek `true` kalıyordu. Nesil sayacı yalnızca gerçekten
 * geçersizleşme durumlarında (kullanıcı değişimi, elle yenileme) artar.
 */
export function useDashboardData(range: RangeKey): DashboardState {
  const userId = useCurrentUserId();
  const { resolvedTheme } = useTheme();
  const canli = isApiConfigured && userId !== null;

  const [temel, setTemel] = useState<TemelVeri | null>(null);
  const [aktifPerformans, setAktifPerformans] = useState<{
    range: RangeKey;
    sonuc: ApiPerformanceResult;
  } | null>(null);
  const [temelYukleniyor, setTemelYukleniyor] = useState(canli);
  const [donemYukleniyor, setDonemYukleniyor] = useState(canli);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // Önbellek ve uçuş takibi REF'te: state olsalardı effect bağımlılığına girer
  // ve yukarıda anlatılan kendi kendini iptal etme sorununu doğururlardı.
  const onbellek = useRef<Partial<Record<RangeKey, ApiPerformanceResult>>>({});
  const ucusta = useRef<Set<RangeKey>>(new Set());
  const nesil = useRef(0);

  // --- Kullanıcı değişimi: her şey geçersiz --------------------------------
  // Başkasının serisi bir an bile gösterilemez (AK 5.4).
  useEffect(() => {
    nesil.current += 1;
    onbellek.current = {};
    ucusta.current = new Set();
    setAktifPerformans(null);
    setTemel(null);
  }, [userId]);

  // --- Temel veri ---------------------------------------------------------
  useEffect(() => {
    if (!canli) {
      setTemelYukleniyor(false);
      return;
    }
    const kullanici = userId!;
    const benimNesil = nesil.current;
    setTemelYukleniyor(true);

    Promise.all([
      fetchPortfolioSummary(kullanici),
      // Bu üçü opsiyonel: düşerlerse `null` ile devam edilir, ekran çizilir.
      // Risk özellikle kırılgan — yeterli fiyat geçmişi yoksa hesaplanamıyor —
      // ve onun yüzünden tüm dashboard'u karartmak doğru olmaz.
      fetchHoldings(kullanici).catch(() => null),
      fetchTransactions(kullanici).catch(() => null),
      fetchRiskAssessment(kullanici).catch(() => null),
    ])
      .then(([ozet, varliklar, islemler, risk]) => {
        if (nesil.current !== benimNesil) return;
        setTemel({ ozet, varliklar, islemler, risk });
        setError(null);
      })
      .catch((err: unknown) => {
        if (nesil.current !== benimNesil) return;
        setTemel(null);
        setError(err instanceof Error ? err.message : "Portföy verisi alınamadı.");
      })
      .finally(() => {
        if (nesil.current === benimNesil) setTemelYukleniyor(false);
      });
  }, [canli, userId, tick]);

  // --- Dönem verisi -------------------------------------------------------
  useEffect(() => {
    if (!canli) {
      setDonemYukleniyor(false);
      return;
    }

    const onbellekten = onbellek.current[range];
    if (onbellekten) {
      // Ağa çıkmadan, anında.
      setAktifPerformans({ range, sonuc: onbellekten });
      setDonemYukleniyor(false);
      return;
    }
    if (ucusta.current.has(range)) {
      // İstek zaten yolda; ikincisini göndermiyoruz.
      return;
    }

    const kullanici = userId!;
    const benimNesil = nesil.current;
    ucusta.current.add(range);
    setDonemYukleniyor(true);

    fetchPerformance(kullanici, WINDOW_BY_RANGE[range])
      .then((sonuc) => {
        if (nesil.current !== benimNesil) return;
        onbellek.current[range] = sonuc;
        setAktifPerformans({ range, sonuc });
      })
      .catch((err: unknown) => {
        if (nesil.current !== benimNesil) return;
        setError(err instanceof Error ? err.message : "Dönem verisi alınamadı.");
      })
      .finally(() => {
        ucusta.current.delete(range);
        if (nesil.current === benimNesil) setDonemYukleniyor(false);
      });
  }, [canli, userId, range, tick]);

  // --- Türetme ------------------------------------------------------------
  //
  // GÖSTERİLEN dönem, İSTENEN dönemden farklı olabilir: yeni dönem yüklenirken
  // bir öncekinin verisi gösterilmeye devam eder. Bu ayrım şart — aksi halde
  // türetme mock veriye düşer ve tüm dashboard (özet kartları, dağılım,
  // işlemler) bir kare boyunca TASARIM VERİSİ gösterirdi.
  const data = useMemo<DashboardData>(() => {
    if (!temel || !aktifPerformans) return mockDashboard;
    return toDashboardData({
      summary: temel.ozet,
      performance: aktifPerformans.sonuc,
      range: aktifPerformans.range,
      holdings: temel.varliklar,
      transactions: temel.islemler,
      risk: temel.risk,
      darkTheme: resolvedTheme === "dark",
    });
  }, [temel, aktifPerformans, resolvedTheme]);

  const canliVeri = temel !== null && aktifPerformans !== null;

  const refetch = useCallback(() => {
    // Elle yenilemede önbellek DE temizlenir: kullanıcı "güncel veriyi getir"
    // diyor, önbellekten okumak bunu boşa çıkarırdı.
    nesil.current += 1;
    onbellek.current = {};
    ucusta.current = new Set();
    setTick((t) => t + 1);
  }, []);

  return {
    data,
    loading: temelYukleniyor && temel === null,
    rangeLoading: donemYukleniyor,
    error,
    isDemoData: !canliVeri,
    freshnessWarning: temel ? priceFreshnessWarning(temel.ozet) : null,
    chartRange: aktifPerformans ? (data.performance[aktifPerformans.range] ?? null) : null,
    refetch,
  };
}
