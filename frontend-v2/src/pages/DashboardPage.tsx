import { useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { dashboardStaggerItem } from "@/components/PageTransition";
import { PageHeading } from "@/components/common/PageHeading";
import { StatCard } from "@/components/dashboard/StatCard";
import { PerformanceChart } from "@/components/dashboard/PerformanceChart";
import { AssetAllocationDonut } from "@/components/dashboard/AssetAllocationDonut";
import { PerformerHighlights } from "@/components/dashboard/PerformerHighlights";
import { TransactionsList } from "@/components/dashboard/TransactionsList";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { InfoTooltip } from "@/components/common/InfoTooltip";
import { DashboardSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { TrendUpIcon } from "@/components/icons";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useAuth } from "@/auth/AuthContext";
import { formatTRY, formatSignedTRY, formatPct, formatNumberTR } from "@/utils/format";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";
import type { RangeKey, ScreenId } from "@/types/finance";

interface DashboardPageProps {
  onNavigate: (screen: ScreenId) => void;
  /** LoginScreen'den gelen ilk mount'ta true — Faz 5: kartlar/grafik sırayla belirir. */
  introSequence?: boolean;
}

/** Faz 5 sırasında bir öğeyi dashboardStaggerItem ile sarmalar; aksi halde olduğu gibi geçer. */
function StaggerItem({ active, children }: { active: boolean; children: ReactNode }) {
  if (!active) return <>{children}</>;
  return <motion.div variants={dashboardStaggerItem}>{children}</motion.div>;
}

/** "Ahmet Yılmaz" → "Ahmet". Selamlamada tam ad fazla resmi duruyor. */
function ilkAd(tamAd: string): string {
  return tamAd.trim().split(/\s+/)[0] ?? "";
}

export function DashboardPage({ introSequence = false }: DashboardPageProps) {
  const [range, setRange] = useState<RangeKey>("1Y");
  const { data, loading, rangeLoading, error, isDemoData, freshnessWarning, chartRange, refetch } =
    useDashboardData(range);
  const { user } = useAuth();
  const shouldReduceMotion = useReducedMotion();
  const stagger = introSequence && !shouldReduceMotion;
  const { summary } = data;

  const ad = ilkAd(user.name);

  // Gerçek veri yokken içerik çizilmez. Hata durumunda da iskelet kalır
  // (kartlar ₺0 göstermesin diye) ama NABIZ ATMAZ: sürekli atan bir iskelet
  // "hâlâ yükleniyor" izlenimi verir, oysa yükleme bitti ve başarısız oldu.
  // Hata bandı iskeletin üstünde zaten görünüyor.
  const ilkYukleme = loading;

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
        <PageHeading
          kicker="Genel Bakış"
          title={ad ? `İyi günler, ${ad}` : "Genel Bakış"}
          description={
            loading ? "Portföy verisi yükleniyor…" : `Fiyatlar ${data.lastUpdated} itibarıyla.`
          }
        />

        {/* Backend'in üç hata kodu üç FARKLI durumdur ve arayüz üçünü ayrı
            göstermeli (docs/API.md): 404 kullanıcı/portföy yok, 409 kaynak var
            ama hesaplanacak veri yok, 403 başkasının verisi. Sunucunun
            gönderdiği metin zaten Türkçe ve bu ayrımı taşıyor, olduğu gibi
            gösteriliyor. */}
        {error && <ErrorBanner message={error} onDismiss={refetch} />}

        {/* Özet her varlığı KENDİ son fiyatıyla değerliyor; tek bir tarih tüm
            portföyü tarif etmiyor. Bir kısmı eskiyse söylenmesi zorunlu,
            yoksa özet olduğundan taze görünür. */}
        {freshnessWarning && (
          <div className="mb-6 rounded-xl border border-line bg-surface-elevated px-4 py-3 text-[13px] text-ink-muted">
            {freshnessWarning}
          </div>
        )}

        {/* Gösterilen veri sunucudan gelmediyse bunu SÖYLEMEK zorundayız;
            uydurma rakamı gerçek sanmak bir finans ürününde en kötü hata
            modu (CLAUDE.md §4). */}
        {isDemoData && !loading && !error && (
          <div className="mb-6 rounded-xl border border-line bg-surface-elevated px-4 py-3 text-[13px] text-ink-muted">
            Bu ekranda <strong className="font-semibold">tasarım verisi</strong> gösteriliyor —
            sunucuya bağlanılamadı.
          </div>
        )}

        {/* Gerçek veri gelmeden içerik ÇİZİLMİYOR. Aksi halde ekran bir
            an tasarım verisiyle doluyor ("stok hali") ve o anda uyarı
            bandı da bastırılmış oluyordu. */}
        {ilkYukleme ? (
          <DashboardSkeleton animated={!error} />
        ) : (
          <>
        <div className="mb-6 grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-4">
          <StaggerItem active={stagger}>
            <StatCard
              label="Toplam Portföy"
              value={formatTRY(summary.totalValue)}
              footer={
                summary.todayChange === undefined ? (
                  // Yeterli geçmiş yoksa backend null döndürüyor; 0 yazmak
                  // "bugün hiç değişmedi" demek olurdu (AK 5.5).
                  <span className="font-medium text-ink-faint">günlük değişim hesaplanamadı</span>
                ) : (
                  <>
                    <TrendUpIcon
                      size={15}
                      className={summary.todayChange >= 0 ? "text-positive" : "text-negative"}
                    />
                    <span className={summary.todayChange >= 0 ? "text-positive" : "text-negative"}>
                      {formatSignedTRY(summary.todayChange)}
                    </span>
                    {/* "bugün" YAZMIYOR, bilerek. Borsa hafta sonu ve tatilde
                        kapalı; Pazartesi bakan kullanıcıya Cuma kapanışına
                        göre değişim gösteriliyor. "bugün" demek, piyasanın
                        kapalı olduğu bir günde yanlış bir iddia olurdu. */}
                    <span className="font-medium text-ink-faint">
                      {data.lastUpdated} kapanışı
                    </span>
                  </>
                )
              }
            />
          </StaggerItem>

          <StaggerItem active={stagger}>
            <StatCard
              label="Toplam Kâr/Zarar"
              value={formatSignedTRY(summary.totalPL)}
              footer={
                <span className={summary.totalPL >= 0 ? "text-positive" : "text-negative"}>
                  {formatPct(summary.totalPLPct)}
                </span>
              }
            />
          </StaggerItem>

          {/* Tasarımdaki "Reel Getiri" kartının yerine: sistemde enflasyon
              kaynağı yok, bu rakamın ise var. Ayrıca docs/API.md yatırılan
              tutarın gösterilmesini şart koşuyor — üç rakam (değer, kâr,
              yatırılan) ancak birlikte tutarlı okunuyor. */}
          <StaggerItem active={stagger}>
            <StatCard
              label="Yatırılan Tutar"
              value={formatTRY(summary.netInvested)}
              footer={
                <>
                  <span className="font-medium text-ink-faint">net sermaye</span>
                  <InfoTooltip text="Dışarıdan koyduğunuz para (yatırma − çekme). Hesapta duran nakit de buna dahildir; kâr/zarar bu tabana göre hesaplanır." />
                </>
              }
            />
          </StaggerItem>

          {/* Risk kartı. Tasarımdaki "Risk Skoru 0-100" DEĞİL: risk
              metodolojisi v2 kompozit skoru bilerek kaldırdı, yerine
              volatiliteden türeyen 7 kademeli etiket geldi. Skoru geri
              getirmek, kaldırılma gerekçesini görmezden gelmek olurdu.

              Dönem getirisi buradan çıkarıldı çünkü grafiğin altındaki
              kutuda zaten var — aynı rakamı iki yerde göstermek kartı
              harcıyordu. */}
          <StaggerItem active={stagger}>
            <StatCard
              label="Risk Seviyesi"
              value={data.risk?.levelLabel ?? "—"}
              footer={
                data.risk?.annualizedVolatilityPct == null ? (
                  // Yeterli fiyat geçmişi yoksa risk UYDURULMAZ (AK 2.7).
                  <span className="font-medium text-ink-faint">
                    {data.risk?.warning ?? "hesaplanamadı"}
                  </span>
                ) : (
                  <>
                    <span className="font-medium text-ink-faint">
                      yıllık %{formatNumberTR(data.risk.annualizedVolatilityPct, 1)} oynaklık
                    </span>
                    {data.risk.withinProfile === false && (
                      <span className="font-semibold text-negative">· profil üstü</span>
                    )}
                    <InfoTooltip
                      text={`Seviye, portföyün yıllık oynaklığından hesaplanır. ${data.risk.profileLabel} profilinin beklenen bandına göre değerlendirilir.`}
                    />
                  </>
                )
              }
            />
          </StaggerItem>
        </div>

        <StaggerItem active={stagger}>
          <div className="mb-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[1.65fr_1fr]">
            {/* KART HER ZAMAN ÇİZİLİR. Önceden `data.performance[range] &&`
                ile korunuyordu ve dönem değişince veri bir anlığına
                `undefined` olduğu için kart DOM'dan kalkıyor, sayfa düzeni
                çöküyor, veri gelince yeniden beliriyordu. Artık yeni dönem
                yüklenirken bir öncekinin serisi gösteriliyor (`chartRange`)
                ve kart hiç unmount olmuyor. */}
            <PerformanceChart
              range={chartRange}
              activeRange={range}
              onRangeChange={setRange}
              loading={rangeLoading}
            />
            <AssetAllocationDonut
              slices={data.allocation}
              instrumentCount={data.instrumentCount}
              assetClassCount={data.assetClassCount}
            />
          </div>
        </StaggerItem>

        <PerformerHighlights best={data.bestPerformer} worst={data.worstPerformer} />

        <div className="grid grid-cols-1 gap-6">
          <TransactionsList transactions={data.transactions} />
        </div>
          </>
        )}

        {/* "Portföyü Yeniden Dengele" ve "Detaylı Rapor Oluştur" butonları
            KALDIRILDI. Mock öneri üretiyorlardı; finansal bir üründe kaynağı
            olmayan tavsiye göstermek en riskli davranış (CLAUDE.md §4).
            Yeniden dengeleme, risk servisinin kural tabanlı senaryo motoru
            REST'e açıldığında gerçek haliyle geri gelecek. */}

        <p className="m-0 mt-8 text-center text-xs italic text-ink-faint">
          {INVESTMENT_DISCLAIMER}
        </p>
      </div>
    </div>
  );
}
