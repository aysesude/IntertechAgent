import { Card } from "@/components/common/Card";
import { InfoTooltip } from "@/components/common/InfoTooltip";
import { formatNumberTR } from "@/utils/format";
import type { RiskDiversification } from "@/types/finance";

interface RiskDiversificationCardProps {
  diversification: RiskDiversification;
}

interface MetricProps {
  label: string;
  value: string;
  /** Her zaman görünür, kısa düz dille açıklama — tooltip'e bağımlı kalmasın. */
  description: string;
  /** Tooltip'teki uzun/teknik açıklama — description'ı tekrarlıyorsa gereksiz, atlanabilir. */
  tooltip?: string;
}

function Metric({ label, value, description, tooltip }: MetricProps) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="text-[11.5px] font-semibold uppercase tracking-[.4px] text-ink-muted">{label}</span>
        {tooltip && <InfoTooltip text={tooltip} />}
      </div>
      <div className="font-display text-[28px] font-bold leading-none">{value}</div>
      <p className="m-0 mt-2 text-[12.5px] leading-[1.5] text-ink-muted">{description}</p>
    </div>
  );
}

export function RiskDiversificationCard({ diversification: d }: RiskDiversificationCardProps) {
  return (
    <Card className="p-6">
      <h2 className="font-display m-0 mb-[18px] text-[17px] font-semibold">Çeşitlendirme</h2>
      {/* Bölücüler koyu temada kaldırılıyor (bkz. Card.tsx/HoldingsTable.tsx'teki
          aynı kural) — ayrım orada da burada da boşluk/tipografiyle sağlanıyor. */}
      <div className="flex flex-col divide-y divide-line2 dark:divide-transparent">
        <div className="pb-5">
          <Metric
            label="Yoğunlaşma Endeksi (HHI)"
            value={formatNumberTR(d.herfindahlIndex, 2)}
            description="0'a yakınsa dengeli dağılmış, 1'e yaklaştıkça birkaç varlıkta yoğunlaşmış demektir."
            tooltip="Herfindahl-Hirschman endeksi (0-1 arası yoğunlaşma ölçütü). Sıfıra yakınsa portföy dengeli dağılmış, 1'e yaklaştıkça birkaç varlıkta yoğunlaşmış demektir."
          />
        </div>
        <div className="py-5">
          <Metric
            label="Çeşitlendirme Oranı"
            value={d.diversificationRatio === null ? "—" : formatNumberTR(d.diversificationRatio, 2)}
            description="1'e yakınsa çeşitlendirme etkisi zayıf, yükseldikçe (1'in üzerinde) riski daha çok azaltıyor demektir."
            tooltip="Varlıkların tek tek volatilitelerinin ağırlıklı toplamının, portföyün BİRLİKTE hareket ederken ortaya çıkan gerçek volatilitesine oranı."
          />
        </div>
        <div className="pt-5">
          <Metric
            label="En Büyük Sınıf Ağırlığı"
            value={`%${formatNumberTR(d.maxClassWeightPct, 1)}${d.maxClassLabel ? ` · ${d.maxClassLabel}` : ""}`}
            description="Portföyünüzdeki en büyük tek varlık sınıfının payı — bu oran yükseldikçe portföy o sınıfa bağımlı hale gelir."
          />
        </div>
      </div>
    </Card>
  );
}
