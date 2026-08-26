import { Card } from "@/components/common/Card";
import { LEVEL_COLORS } from "@/components/dashboard/RiskLevelBar";
import { formatNumberTR } from "@/utils/format";
import type { RiskAssetRow } from "@/types/finance";

interface RiskAssetsTableProps {
  assets: RiskAssetRow[];
}

const COLUMNS = ["Sembol", "Sınıf", "Ağırlık", "Volatilite", "Risk Seviyesi"];

/**
 * `HoldingsTable.tsx` ile aynı görsel dil (başlık/satır/hücre sınıfları) —
 * ama risk rozeti farklı bir ölçek kullanıyor: burada Düşük/Orta/Yüksek (3
 * kademe, tema rengiyle tonlu) değil, `RiskLevelBar`'daki 7 kademeli
 * yeşil→kırmızı rampa (`LEVEL_COLORS`) — ikisi aynı anlama gelmiyor, aynı
 * rozet stilini kullanmak yanlış bir eşleşmeymiş gibi okunurdu.
 */
export function RiskAssetsTable({ assets }: RiskAssetsTableProps) {
  return (
    <Card className="p-6">
      <h2 className="font-display m-0 mb-[18px] text-[17px] font-semibold">Varlık Bazlı Risk</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse">
          <thead>
            <tr className="text-left">
              {COLUMNS.map((h, i) => (
                <th
                  key={h}
                  className={`pb-[11px] text-[11px] font-semibold uppercase tracking-[.7px] text-ink-faint ${
                    i >= 2 ? "text-right" : ""
                  }`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {assets.map((a) => (
              <tr key={a.symbol} className="border-t border-line2 dark:border-transparent">
                <td className="py-3.5 text-sm font-semibold">{a.symbol}</td>
                <td className="py-3.5 text-[13.5px] text-ink-soft">{a.assetClassLabel}</td>
                <td className="py-3.5 text-right text-[13.5px] text-ink-soft">%{formatNumberTR(a.weightPct, 1)}</td>
                <td className="py-3.5 text-right text-[13.5px] text-ink-soft">
                  {a.volatilityPct === null ? "—" : `%${formatNumberTR(a.volatilityPct, 1)}`}
                </td>
                <td className="py-3.5 text-right">
                  {a.riskLevelLabel === null || a.riskLevelOrdinal === null ? (
                    <span className="rounded-md bg-line2 px-2.5 py-1 text-[11.5px] font-semibold text-ink-faint">—</span>
                  ) : (
                    <span
                      className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold text-white"
                      style={{ background: LEVEL_COLORS[a.riskLevelOrdinal - 1] }}
                    >
                      {a.riskLevelLabel}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
