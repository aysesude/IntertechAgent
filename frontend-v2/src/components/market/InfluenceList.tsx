import { useState } from "react";
import type { InfluenceRow } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { formatPct } from "@/utils/format";
import { POSITIVE, NEGATIVE, LINE2, FIXED_DARK_CHIP } from "@/utils/colors";

interface InfluenceListProps {
  rows: InfluenceRow[];
}

export function InfluenceList({ rows }: InfluenceListProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  // Ağırlığı bilinmeyen satır (fiyatı bulunamamış varlık) ölçeğe girmez;
  // hiç ağırlık yoksa `1` ile bölünüp tüm çubuklar boş kalır — `Math.max()`
  // boş dizide `-Infinity` döndürüp NaN genişlik üretiyordu.
  const agirliklar = rows.map((r) => r.weightPct).filter((w): w is number => w !== null);
  const maxWeight = agirliklar.length > 0 ? Math.max(...agirliklar) : 1;

  return (
    <Card className="p-[22px]">
      <h2 className="font-display m-0 mb-4 text-base font-semibold">Portföyünü Etkileyenler</h2>
      <div className="mb-2 flex items-center gap-3">
        <span className="w-[58px]" />
        <span className="flex-1 text-[11px] font-semibold uppercase tracking-[.4px] text-ink-faint">Portföy Ağırlığı</span>
        <span className="w-[52px]" />
      </div>
      <div className="flex flex-col gap-[13px]">
        {rows.map((row) => {
          // Değişim bilinmiyorsa çubuk nötr çizilir; yukarı/aşağı rengi
          // vermek olmayan bir yön iddia etmek olurdu.
          const up = row.changePct !== null && row.changePct >= 0;
          const yonRengi = row.changePct === null ? LINE2 : up ? POSITIVE : NEGATIVE;
          const widthPct = ((row.weightPct ?? 0) / maxWeight) * 100;
          return (
            <div
              key={row.id}
              className="relative flex items-center gap-3"
              onMouseEnter={() => setHovered(row.id)}
              onMouseLeave={() => setHovered(null)}
            >
              <span className="font-display w-[58px] truncate text-[13px] font-bold" title={row.name}>
                {row.name}
              </span>
              <div className="h-[5px] flex-1 cursor-pointer overflow-hidden rounded-full" style={{ backgroundColor: LINE2 }}>
                <div className="h-full" style={{ width: `${widthPct}%`, background: yonRengi }} />
              </div>
              <span
                className="w-[52px] text-right text-[12.5px] font-semibold"
                style={{ color: yonRengi }}
              >
                {row.changePct === null ? "—" : formatPct(row.changePct)}
              </span>
              {hovered === row.id && row.weightPct !== null && (
                <div
                  className="animate-tipIn absolute bottom-[calc(100%+6px)] left-[58px] z-10 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold text-white"
                  style={{ backgroundColor: FIXED_DARK_CHIP }}
                >
                  Portföyün %{row.weightPct}'i
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
