import { PageHeading } from "@/components/common/PageHeading";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { RiskOverviewStrip } from "@/components/risk/RiskOverviewStrip";
import { RiskContributionList } from "@/components/risk/RiskContributionList";
import { RiskDiversificationCard } from "@/components/risk/RiskDiversificationCard";
import { RiskAssetsTable } from "@/components/risk/RiskAssetsTable";
import { RiskMetricsRow } from "@/components/risk/RiskMetricsRow";
import { useRiskData } from "@/hooks/useRiskData";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";

export function RiskPage() {
  const { data, loading, error, isDemoData, refetch } = useRiskData();

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Profil"
        title="Risk Analizi"
        description={
          loading
            ? "Risk verisi yükleniyor…"
            : "Seviye, portföyün ÖLÇÜLEN yıllık oynaklığından (7 kademeli) hesaplanır — 0-100 kompozit skor değil."
        }
      />

      {/* Backend'in üç hata kodu üç FARKLI durumdur (bkz. DashboardPage,
          docs/API.md) — sunucunun gönderdiği metin Türkçe ve bu ayrımı
          taşıyor, olduğu gibi gösteriliyor. */}
      {error && <ErrorBanner message={error} onDismiss={refetch} />}

      {/* Gösterilen veri sunucudan gelmediyse bunu SÖYLEMEK zorundayız —
          uydurma rakamı gerçek sanmak bir finans ürününde en kötü hata
          modu (CLAUDE.md §4). */}
      {isDemoData && !loading && !error && (
        <div className="mb-6 rounded-xl border border-line bg-surface-elevated px-4 py-3 text-[13px] text-ink-muted dark:border-transparent">
          Bu ekranda <strong className="font-semibold">tasarım verisi</strong> gösteriliyor —
          sunucuya bağlanılamadı.
        </div>
      )}

      {/* Gerçek veri gelmeden içerik ÇİZİLMİYOR (bkz. DashboardPage'deki
          aynı gerekçe) — henüz bu sayfaya özel bir iskelet yok, basit bir
          yükleniyor metni yeterli. */}
      {loading ? (
        <p className="m-0 py-10 text-center text-sm text-ink-faint">Yükleniyor…</p>
      ) : (
        <>
          <RiskOverviewStrip overview={data.overview} />

          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[1.35fr_1fr]">
            <RiskContributionList contributions={data.contributions} />
            <RiskDiversificationCard diversification={data.diversification} />
          </div>

          <div className="mb-4">
            <RiskAssetsTable assets={data.assets} />
          </div>

          <RiskMetricsRow valueAtRisk={data.valueAtRisk} sharpe={data.sharpe} warnings={data.warnings} />

          <p className="m-0 mt-4 text-center text-xs italic text-ink-soft dark:text-ink-faint">
            {INVESTMENT_DISCLAIMER}
          </p>
        </>
      )}
      </div>
    </div>
  );
}
