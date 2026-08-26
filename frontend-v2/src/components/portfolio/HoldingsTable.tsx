import { useState, type KeyboardEvent } from "react";
import { AnimatePresence } from "framer-motion";
import type { Holding } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { LEVEL_COLORS } from "@/components/dashboard/RiskLevelBar";
import { formatPct } from "@/utils/format";
import { POSITIVE, NEGATIVE } from "@/utils/colors";
import { HoldingReturnDetail } from "@/components/portfolio/HoldingReturnDetail";

const FILTERS = ["Hisse", "Emtia", "Tümü"] as const;

// Türkçe etiketi ayrıştırmak yerine kararlı `assetClassId` üzerinden filtrele
// — "Hisse · Savunma" gibi alt kırılımlı etiketler backend'den gelmiyor,
// prefix eşleşmesi gerçek veriyle sessizce kırılırdı.
function classForHolding(holding: Holding, filter: (typeof FILTERS)[number]) {
  if (filter === "Tümü") return true;
  if (filter === "Hisse") return holding.assetClassId === "stocks";
  return holding.assetClassId === "precious";
}

interface HoldingsTableProps {
  holdings: Holding[];
}

export function HoldingsTable({ holdings }: HoldingsTableProps) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("Tümü");
  const [selected, setSelected] = useState<Holding | null>(null);
  const visible = holdings.filter((h) => classForHolding(h, filter));

  function handleRowKeyDown(e: KeyboardEvent<HTMLTableRowElement>, holding: Holding) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setSelected(holding);
    }
  }

  return (
    <Card className="p-6">
      <div className="mb-[18px] flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display m-0 text-[17px] font-semibold">Pozisyonlar</h2>
        <div className="flex gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={
                "min-h-10 rounded-lg px-[13px] py-[7px] text-xs font-semibold transition-colors " +
                (f === filter ? "bg-brand text-white" : "border border-line text-ink-muted dark:border-transparent dark:bg-white/5")
              }
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse">
          <thead>
            <tr className="text-left">
              {["Enstrüman", "Adet", "Değer", "Getiri", "Risk"].map((h, i) => (
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
            {visible.map((h) => {
              // Getiri detay paneli parti/lot kırılımı gösteriyor
              // (HoldingReturnDetail); backend'de bu ucun karşılığı yok, o
              // yüzden `lots` her zaman boş geliyor (bkz. adapters/portfolio.ts).
              // Panel boş bir kırılımla açılıp yanıltmak yerine satır
              // tamamen tıklanamaz kalıyor — backend lot ucu geldiğinde bu
              // koşulu kaldırmak yeterli olacak.
              const detayVar = h.lots.length > 0;
              return (
                <tr
                  key={h.id}
                  role={detayVar ? "button" : undefined}
                  tabIndex={detayVar ? 0 : undefined}
                  aria-label={detayVar ? `${h.name} için getiri detaylarını aç` : undefined}
                  onClick={detayVar ? () => setSelected(h) : undefined}
                  onKeyDown={detayVar ? (e) => handleRowKeyDown(e, h) : undefined}
                  className={
                    "border-t border-line2 transition-colors dark:border-transparent " +
                    (detayVar ? "cursor-pointer hover:bg-black/[0.02] dark:hover:bg-white/[0.04]" : "")
                  }
                >
                  <td className="py-3.5">
                    <div className="text-sm font-semibold">{h.name}</div>
                    <div className="text-xs text-ink-faint">{h.assetClass}</div>
                  </td>
                  <td className="py-3.5 text-[13.5px] text-ink-soft">{h.quantity}</td>
                  <td className="py-3.5 text-right text-[13.5px] font-semibold">{h.formattedValue}</td>
                  <td className="py-3.5 text-right">
                    {h.returnPct === null ? (
                      <span className="text-[13.5px] font-semibold text-ink-faint">—</span>
                    ) : (
                      <span
                        className="text-[13.5px] font-semibold"
                        style={{ color: h.returnPct >= 0 ? POSITIVE : NEGATIVE }}
                      >
                        {formatPct(h.returnPct)}
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 text-right">
                    {/* Risk sütunu /holdings'ten DEĞİL, /api/risk'teki
                        asset_metrics[]'ten geliyor (bkz. adapters/portfolio.ts).
                        7 kademeli ölçek — Risk sayfasındaki RiskAssetsTable ile
                        aynı LEVEL_COLORS rampası, aynı anlam. */}
                    {h.risk === null || h.riskOrdinal === null ? (
                      <span className="rounded-md bg-line2 px-2.5 py-1 text-[11.5px] font-semibold text-ink-faint">
                        —
                      </span>
                    ) : (
                      <span
                        className="rounded-md px-2.5 py-1 text-[11.5px] font-semibold text-white"
                        style={{ background: LEVEL_COLORS[h.riskOrdinal - 1] }}
                      >
                        {h.risk}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {selected && <HoldingReturnDetail key={selected.id} holding={selected} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </Card>
  );
}
