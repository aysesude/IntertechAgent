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
 * MODÜL DÜZEYİNDE önbellek — sayfalar arası gezinmede hayatta kalır.
 *
 * Hook, Dashboard'dan çıkılınca unmount oluyor ve tüm state sıfırlanıyordu;
 * geri dönüldüğünde veri yeniden çekilene kadar TASARIM VERİSİ görünüyordu
 * ("sayfanın stok hali"). Üstelik yükleme sırasında "tasarım verisi" uyarısı
 * da bastırıldığı için uydurma rakamlar uyarısız görünüyordu — bir finans
 * ürününde en kötü hata modu (CLAUDE.md §4).
 *
 * React state'i bunu çözemez çünkü sorun tam olarak state'in kaybolması.
 * Context'e taşımak da olurdu ama o, veriyi Dashboard'a ihtiyacı olmayan
 * ekranların ağacına da sokardı. Modül değişkeni en dar çözüm.
 *
 * Kullanıcıya bağlı: başkasının verisi bir an bile gösterilemez (AK 5.4).
 * Oturum kapanınca ağaç unmount olur ama modül hayatta kalır, o yüzden
 * `userId` eşleşmesi zorunlu.
 */
let paylasilanOnbellek: {
  userId: string;
  temel: TemelVeri;
  performans: Partial<Record<RangeKey, ApiPerformanceResult>>;
} | null = null;

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
/**
 * Veri gelmeden önce kullanılan BOŞ kabuk.
 *
 * Sayısal alanlar sıfır ama ekranda gösterilmiyorlar: `loading` true iken
 * DashboardPage iskelet çiziyor. Buradaki değerlerin görünmesi bir hatadır,
 * "portföyünüz 0 TL" demek olurdu.
 */
const BOS_DASHBOARD: DashboardData = {
  summary: { totalValue: 0, costBasis: 0, netInvested: 0, totalPL: 0, totalPLPct: 0 },
  performance: {} as DashboardData["performance"],
  allocation: [],
  transactions: [],
  recommendations: [],
  instrumentCount: 0,
  assetClassCount: 0,
  lastUpdated: "",
};

/**
 * Modül önbelleğini boşaltır. YALNIZCA TESTLER İÇİN.
 *
 * Modül değişkeni test dosyası boyunca yaşar; sıfırlanmazsa bir testin
 * çektiği veri diğerine sızar ve testler birbirini gizler.
 */
export function __dashboardOnbelleginiSifirla(): void {
  paylasilanOnbellek = null;
}

export function useDashboardData(range: RangeKey): DashboardState {
  const userId = useCurrentUserId();
  const { resolvedTheme } = useTheme();
  const canli = isApiConfigured && userId !== null;

  // Önbellekte bu kullanıcıya ait veri varsa ekran BOŞ AÇILMAZ.
  const onbellekGecerli = paylasilanOnbellek?.userId === userId;

  const [temel, setTemel] = useState<TemelVeri | null>(
    onbellekGecerli ? paylasilanOnbellek!.temel : null,
  );
  const [aktifPerformans, setAktifPerformans] = useState<{
    range: RangeKey;
    sonuc: ApiPerformanceResult;
  } | null>(() => {
    if (!onbellekGecerli) return null;
    const sonuc = paylasilanOnbellek!.performans[range];
    return sonuc ? { range, sonuc } : null;
  });
  const [donemYukleniyor, setDonemYukleniyor] = useState(canli && !onbellekGecerli);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // Önbellek ve uçuş takibi REF'te: state olsalardı effect bağımlılığına girer
  // ve yukarıda anlatılan kendi kendini iptal etme sorununu doğururlardı.
  const onbellek = useRef<Partial<Record<RangeKey, ApiPerformanceResult>>>(
    onbellekGecerli ? { ...paylasilanOnbellek!.performans } : {},
  );
  const ucusta = useRef<Set<RangeKey>>(new Set());
  const nesil = useRef(0);

  // --- Kullanıcı değişimi: her şey geçersiz --------------------------------
  // Başkasının serisi bir an bile gösterilemez (AK 5.4).
  useEffect(() => {
    if (paylasilanOnbellek?.userId === userId) return; // aynı kullanıcı, veri geçerli
    nesil.current += 1;
    onbellek.current = {};
    ucusta.current = new Set();
    paylasilanOnbellek = null;
    setAktifPerformans(null);
    setTemel(null);
  }, [userId]);

  // --- Temel veri ---------------------------------------------------------
  useEffect(() => {
    if (!canli) return;
    const kullanici = userId!;
    const benimNesil = nesil.current;

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
        const yeniTemel = { ozet, varliklar, islemler, risk };
        setTemel(yeniTemel);
        paylasilanOnbellek = {
          userId: kullanici,
          temel: yeniTemel,
          performans: { ...onbellek.current },
        };
        setError(null);
      })
      .catch((err: unknown) => {
        if (nesil.current !== benimNesil) return;
        setTemel(null);
        setError(err instanceof Error ? err.message : "Portföy verisi alınamadı.");
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
        // Dönem serisi de gezinmeye dayanmalı; aksi halde geri dönüldüğünde
        // grafik yeniden yüklenirdi.
        if (paylasilanOnbellek?.userId === kullanici) {
          paylasilanOnbellek.performans = { ...onbellek.current };
        }
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
    // API bağlıyken gerçek veri gelene kadar TASARIM VERİSİ DÖNMÜYOR.
    // Döndüğünde ekran bir an "stok hali"ni gösteriyordu ve o anda uyarı
    // bandı da bastırılmış oluyordu, yani uydurma rakamlar uyarısız
    // görünüyordu. Sayfa bu durumda iskelet çiziyor (bkz. DashboardPage).
    //
    // ÖZET YETER, SERİ ŞART DEĞİL. Eskiden ikisi birden aranıyordu ve
    // performans ucu düştüğünde ekran sonsuza kadar iskelet kalıyordu —
    // bugün açılan bir hesap ilk alımını yapar yapmaz tam olarak bunu
    // yaşıyordu (uç `InsufficientDataError` fırlatıyordu; asıl sebep
    // sunucuda düzeltildi). Tek bir ucun düşmesi tüm ekranı karartmamalı
    // (CLAUDE.md §4 zarif düşüş).
    if (!temel) return canli ? BOS_DASHBOARD : mockDashboard;
    return toDashboardData({
      summary: temel.ozet,
      performance: aktifPerformans?.sonuc ?? null,
      range: aktifPerformans?.range ?? range,
      holdings: temel.varliklar,
      transactions: temel.islemler,
      risk: temel.risk,
      darkTheme: resolvedTheme === "dark",
    });
  }, [temel, aktifPerformans, range, resolvedTheme, canli]);

  // Gerçek veri var mı: ÖZET belirleyici. Seri olmadan da ekran gerçek
  // rakamları gösteriyor, dolayısıyla "tasarım verisi" uyarısı yanlış olurdu.
  const canliVeri = temel !== null;

  const refetch = useCallback(() => {
    // Elle yenilemede önbellek DE temizlenir: kullanıcı "güncel veriyi getir"
    // diyor, önbellekten okumak bunu boşa çıkarırdı.
    nesil.current += 1;
    onbellek.current = {};
    ucusta.current = new Set();
    paylasilanOnbellek = null;
    setTick((t) => t + 1);
  }, []);

  return {
    data,
    // "Gösterilecek GERÇEK veri henüz yok" demek — yalnızca ilk yükleme.
    // Ayrı bir `temelYukleniyor` bayrağına bakmak yetmiyordu: özet gelip dönem serisi
    // hâlâ yoldayken `data` boş kabuğa düşüyor ve kartlar bir kare boyunca
    // ₺0 gösteriyordu ("portföyünüz 0 ₺" demek olurdu). Dönem DEĞİŞİMİ bunu
    // tetiklemez, çünkü o sırada `temel` ve önceki seri elde duruyor.
    loading: canli && !canliVeri,
    rangeLoading: donemYukleniyor,
    error,
    isDemoData: !canliVeri,
    freshnessWarning: temel ? priceFreshnessWarning(temel.ozet) : null,
    chartRange: aktifPerformans ? (data.performance[aktifPerformans.range] ?? null) : null,
    refetch,
  };
}
