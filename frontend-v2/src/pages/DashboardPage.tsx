import { useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { dashboardStaggerItem } from "@/components/PageTransition";
import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/common/Button";
import { Card } from "@/components/common/Card";
import { StatCard } from "@/components/dashboard/StatCard";
import { PerformanceChart } from "@/components/dashboard/PerformanceChart";
import { AssetAllocationDonut } from "@/components/dashboard/AssetAllocationDonut";
import { PerformerHighlights } from "@/components/dashboard/PerformerHighlights";
import { TransactionsList } from "@/components/dashboard/TransactionsList";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { InfoTooltip } from "@/components/common/InfoTooltip";
import { RefreshIcon, FileTextIcon, TrendUpIcon, SparkleIcon } from "@/components/icons";
import { useDashboardData } from "@/hooks/useDashboardData";
import { formatTRY, formatSignedTRY, formatPct } from "@/utils/format";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";
import { RISK_BAND } from "@/data/insightConfig";
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

const ACTION_DELAY_MS = 1200;
// Butonların hata senaryosunu göstermek için simüle edilen başarısızlık
// oranı (AK-3.14, AK-1.12) — gerçek bir API çağrısında ağ/istemci hatası.
const SIMULATED_FAILURE_RATE = 0.2;

function simulateAction(): Promise<void> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (Math.random() < SIMULATED_FAILURE_RATE) reject(new Error("simulated_failure"));
      else resolve();
    }, ACTION_DELAY_MS);
  });
}

export function DashboardPage({ onNavigate, introSequence = false }: DashboardPageProps) {
  const { data } = useDashboardData();
  const shouldReduceMotion = useReducedMotion();
  const stagger = introSequence && !shouldReduceMotion;
  const [range, setRange] = useState<RangeKey>("1Y");
  const [rebalancing, setRebalancing] = useState(false);
  const [showRebalanceResult, setShowRebalanceResult] = useState(false);
  const [rebalanceError, setRebalanceError] = useState<string | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const { summary } = data;

  const handleRebalance = async () => {
    setRebalancing(true);
    setRebalanceError(null);
    setShowRebalanceResult(false);
    try {
      await simulateAction();
      setShowRebalanceResult(true);
    } catch {
      setRebalanceError("Öneri oluşturulamadı, lütfen tekrar deneyin.");
    } finally {
      setRebalancing(false);
    }
  };

  const handleGenerateReport = async () => {
    setGeneratingReport(true);
    setReportError(null);
    try {
      await simulateAction();
    } catch {
      setReportError("Rapor oluşturulamadı, lütfen tekrar deneyin.");
    } finally {
      setGeneratingReport(false);
    }
  };

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Genel Bakış"
        title="İyi günler, Elif"
        description={`Son güncelleme ${data.lastUpdated}.`}
        actions={
          <>
            <Button icon={<RefreshIcon size={17} />} loading={rebalancing} onClick={handleRebalance}>
              Portföyü Yeniden Dengele
            </Button>
            <Button variant="secondary" icon={<FileTextIcon size={17} />} loading={generatingReport} onClick={handleGenerateReport}>
              Detaylı Rapor Oluştur
            </Button>
          </>
        }
      />

      {rebalanceError && <ErrorBanner message={rebalanceError} onDismiss={() => setRebalanceError(null)} />}
      {reportError && <ErrorBanner message={reportError} onDismiss={() => setReportError(null)} />}

      {showRebalanceResult && (
        <Card className="animate-fadeUp mb-6 border-brand-border bg-brand-tint p-6">
          <div className="mb-3 flex items-center gap-2.5">
            <span className="text-brand">
              <SparkleIcon size={18} />
            </span>
            <h2 className="font-display m-0 text-[16px] font-semibold">Yeniden Dengeleme Önerisi</h2>
          </div>
          <div className="mb-1.5 text-sm font-semibold">{data.recommendations[0].title}</div>
          <p className="m-0 text-[13px] leading-[1.55] text-ink-muted">{data.recommendations[0].description}</p>
          <button
            onClick={() => onNavigate("portfolio")}
            className="mt-3.5 text-[13px] font-semibold text-brand hover:underline"
          >
            Portföyde görüntüle →
          </button>
          <p className="m-0 mt-3 text-[11px] italic text-ink-faint">{INVESTMENT_DISCLAIMER}</p>
        </Card>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-4">
        <StaggerItem active={stagger}>
          <StatCard
            label="Toplam Portföy"
            value={formatTRY(summary.totalValue)}
            footer={
              <>
                <TrendUpIcon size={15} className="text-positive" />
                <span className="text-positive">{formatSignedTRY(summary.todayChange)}</span>
                <span className="font-medium text-ink-faint">bugün</span>
              </>
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
        <StaggerItem active={stagger}>
          <StatCard
            label="Reel Getiri (yıllık)"
            value={formatPct(summary.realReturnPct)}
            footer={
              <>
                <span className="font-medium text-ink-faint">enflasyon sonrası</span>
                <InfoTooltip text="Nominal getiriden yıllık enflasyon varsayımı düşülerek hesaplanır." />
              </>
            }
          />
        </StaggerItem>
        <StaggerItem active={stagger}>
          <StatCard
            label="Risk Skoru"
            value={`${summary.riskScore}`}
            footer={<span className="text-[16px] font-semibold text-ink-faint">/100 · hedef {RISK_BAND.low}–{RISK_BAND.high}</span>}
            progress={summary.riskScore}
          />
        </StaggerItem>
      </div>

      <StaggerItem active={stagger}>
        <div className="mb-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[1.65fr_1fr]">
          <PerformanceChart range={data.performance[range]} activeRange={range} onRangeChange={setRange} />
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
      </div>
    </div>
  );
}
