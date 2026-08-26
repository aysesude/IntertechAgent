import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/common/Card";
import { InfoTooltip } from "@/components/common/InfoTooltip";
import { formatNumberTR } from "@/utils/format";
import type { SharpeRatio, ValueAtRisk } from "@/types/finance";

interface RiskMetricsRowProps {
  valueAtRisk: ValueAtRisk;
  sharpe: SharpeRatio;
  /** Backend serbest metin döndürüyor — yapılandırılmış alan yok, düz liste. */
  warnings: string[];
}

export function RiskMetricsRow({ valueAtRisk, sharpe, warnings }: RiskMetricsRowProps) {
  return (
    <div className="mb-4">
      {warnings.length > 0 && (
        <div className="mb-3 flex flex-col gap-2 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800 dark:border-transparent dark:bg-amber-900/20 dark:text-amber-200">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="p-6">
          <div className="mb-1.5 flex items-center gap-1.5">
            <h2 className="font-display m-0 text-[15.5px] font-semibold">Riske Maruz Değer (VaR)</h2>
            <InfoTooltip
              text={`VaR nedir? %${valueAtRisk.confidencePct} güven aralığında, ${valueAtRisk.horizonLabel} normal koşullarda kaybedebileceğin tahmini en yüksek tutardır. Sade dille: "kötü bir günde en fazla ne kadar kaybedebilirim?" sorusunun yanıtı.`}
            />
          </div>
          <div className="font-display text-[26px] font-bold text-danger">{valueAtRisk.formattedAmount}</div>
          <p className="m-0 mt-1.5 text-[12.5px] text-ink-muted">
            %{valueAtRisk.confidencePct} güven aralığında, {valueAtRisk.horizonLabel} olası maksimum kayıp.
          </p>
        </Card>
        <Card className="p-6">
          <div className="mb-1.5 flex items-center gap-1.5">
            <h2 className="font-display m-0 text-[15.5px] font-semibold">Sharpe Oranı</h2>
            <InfoTooltip text="Sharpe Oranı nedir? Aldığın risk karşılığında ne kadar getiri elde ettiğini gösterir. Aşağıdaki not, sayıyı tek başına yorumlamanın neden yanıltıcı olabileceğini açıklıyor." />
          </div>
          <div className="font-display text-[26px] font-bold text-brand">
            {sharpe.value === null ? "—" : formatNumberTR(sharpe.value, 2)}
          </div>
          {/* "İyi/Kötü" gibi bir derecelendirme BİLEREK yok — bkz. adapters/risk.ts:toSharpe. */}
          <p className="m-0 mt-1.5 text-[12.5px] text-ink-muted">{sharpe.note}</p>
        </Card>
      </div>
    </div>
  );
}
