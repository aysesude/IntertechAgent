import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/common/Card";
import { InfoTooltip } from "@/components/common/InfoTooltip";
import type { LimitedHistoryWarning, SharpeRatio, ValueAtRisk } from "@/types/finance";

interface RiskMetricsRowProps {
  valueAtRisk: ValueAtRisk;
  sharpeRatio: SharpeRatio;
  limitedHistoryWarning?: LimitedHistoryWarning;
}

export function RiskMetricsRow({ valueAtRisk, sharpeRatio, limitedHistoryWarning }: RiskMetricsRowProps) {
  return (
    <div className="mb-4">
      {limitedHistoryWarning && (
        <div className="mb-3 flex items-start gap-2.5 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">{limitedHistoryWarning.message}</div>
            <div className="mt-0.5 text-[12px] text-amber-700 dark:text-amber-300">İlgili varlık: {limitedHistoryWarning.assetName}</div>
          </div>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="p-6">
          <div className="mb-1.5 flex items-center gap-1.5">
            <h2 className="font-display m-0 text-[15.5px] font-semibold">Riske Maruz Değer (VaR)</h2>
            <InfoTooltip
              text={`VaR nedir? %${valueAtRisk.confidencePct} güven aralığında, ${valueAtRisk.horizonLabel} normal koşullarda kaybedebileceğin tahmini en yüksek tutardır. Sade dille: "kötü bir ayda en fazla ne kadar kaybedebilirim?" sorusunun yanıtı.`}
            />
          </div>
          <div className="font-display text-[26px] font-bold text-danger">{valueAtRisk.formattedAmount}</div>
          <p className="m-0 mt-1.5 text-[12.5px] text-ink-faint">
            %{valueAtRisk.confidencePct} güven aralığında, {valueAtRisk.horizonLabel} olası maksimum kayıp.
          </p>
        </Card>
        <Card className="p-6">
          <div className="mb-1.5 flex items-center gap-1.5">
            <h2 className="font-display m-0 text-[15.5px] font-semibold">Sharpe Oranı</h2>
            <InfoTooltip text="Sharpe Oranı nedir? Aldığın risk karşılığında ne kadar getiri elde ettiğini gösterir. Sade dille: sayı ne kadar yüksekse, katlanılan risk o kadar iyi karşılığını veriyor demektir. 1'in üzeri iyi, 2'nin üzeri çok iyi kabul edilir." />
          </div>
          <div className="font-display text-[26px] font-bold text-brand">{sharpeRatio.value.toFixed(2).replace(".", ",")}</div>
          <p className="m-0 mt-1.5 text-[12.5px] text-ink-faint">
            {sharpeRatio.rating} · {sharpeRatio.description}
          </p>
        </Card>
      </div>
    </div>
  );
}
