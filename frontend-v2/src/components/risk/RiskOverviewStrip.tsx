import { Card } from "@/components/common/Card";
import { RiskLevelBar } from "@/components/dashboard/RiskLevelBar";
import type { RiskOverview } from "@/types/finance";

interface RiskOverviewStripProps {
  overview: RiskOverview;
}

/**
 * Sayfanın ana mesajı: profil, ÖLÇÜLEN seviye ve ikisinin uyumu tek
 * cümlede. 0-100 kompozit skor/ibre YOK — Risk v2'de bilerek kaldırıldı
 * (bkz. docs/API.md), bu şerit onun yerine geçiyor.
 */
export function RiskOverviewStrip({ overview }: RiskOverviewStripProps) {
  return (
    <Card className="mb-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="m-0 text-[11.5px] font-semibold uppercase tracking-[.5px] text-ink-muted">Risk Profiliniz</p>
          <p className="font-display m-0 mt-1 text-[22px] font-bold">{overview.profileLabel}</p>
        </div>
        <div className="text-right">
          <p className="m-0 text-[11.5px] font-semibold uppercase tracking-[.5px] text-ink-muted">Ölçülen Seviye</p>
          <p className="font-display m-0 mt-1 text-[22px] font-bold">{overview.levelLabel ?? "—"}</p>
        </div>
      </div>
      {overview.level !== null && (
        <div className="mt-1 max-w-[320px]">
          <RiskLevelBar level={overview.level} />
        </div>
      )}
      <p
        className={`m-0 mt-4 text-[13.5px] font-medium ${
          overview.isWithinProfile === false ? "text-danger" : "text-ink-soft"
        }`}
      >
        {overview.verdict}
      </p>
    </Card>
  );
}
