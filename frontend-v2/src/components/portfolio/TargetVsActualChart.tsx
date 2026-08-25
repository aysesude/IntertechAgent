import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertCircle } from "lucide-react";
import type { TargetVsActualRow } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { InfoTooltip } from "@/components/common/InfoTooltip";
import { BRAND, DANGER, INK_FAINT, INK_SOFT, LINE2, SURFACE_ELEVATED, FIXED_DARK_CHIP } from "@/utils/colors";

const DOMAIN_MAX = 50;
const ALERT_ICON_RADIUS = 9;
const ALERT_ICON_GAP = 5;

interface TargetVsActualChartProps {
  rows: TargetVsActualRow[];
}

function ActualBarShape(props: any) {
  const { x, y, width, height, background, payload } = props;
  const isFar = Math.abs(payload.diff) > 4;
  const barColor = isFar ? DANGER : BRAND;
  const targetX = background.x + (payload.targetPct / DOMAIN_MAX) * background.width;
  const endX = x + width;
  const centerY = y + height / 2;
  const isGold = payload.id === "gold";

  return (
    <g>
      <rect x={background.x} y={y} width={background.width} height={height} rx={4} fill={LINE2} />
      <rect x={x} y={y} width={width} height={height} rx={4} fill={barColor} />
      <line x1={targetX} x2={targetX} y1={y - 4} y2={y + height + 4} stroke={INK_SOFT} strokeWidth={2} />
      {isGold ? (
        <g transform={`translate(${endX + ALERT_ICON_GAP}, ${centerY - ALERT_ICON_RADIUS})`}>
          <circle cx={ALERT_ICON_RADIUS} cy={ALERT_ICON_RADIUS} r={ALERT_ICON_RADIUS} fill={SURFACE_ELEVATED} />
          <AlertCircle
            x={ALERT_ICON_RADIUS - 8}
            y={ALERT_ICON_RADIUS - 8}
            width={16}
            height={16}
            color={DANGER}
            strokeWidth={2.4}
          />
        </g>
      ) : (
        <circle cx={endX} cy={centerY} r={6} fill={BRAND} stroke={SURFACE_ELEVATED} strokeWidth={2} />
      )}
    </g>
  );
}

function TvTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: TargetVsActualRow = payload[0].payload;
  const text = row.diff === 0 ? "Hedefte" : `Hedeften ${row.diff > 0 ? "+" : ""}${row.diff} puan ${row.diff > 0 ? "üstte" : "altta"}`;
  return (
    <div className="whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-semibold text-white" style={{ backgroundColor: FIXED_DARK_CHIP }}>
      {text}
    </div>
  );
}

export function TargetVsActualChart({ rows }: TargetVsActualChartProps) {
  return (
    <Card className="animate-fadeUp p-6">
      <div className="mb-4 flex items-center gap-1.5">
        <h2 className="font-display m-0 text-[17px] font-semibold">Hedef vs Gerçekleşen</h2>
        <InfoTooltip text="Her varlık sınıfı için iki değeri karşılaştırır: ne kadarına sahip olmanız hedeflendi, ne kadarına şu an gerçekten sahipsiniz. Çubuk gerçek durumunuzu, üzerindeki dikey çizgi ise hedefi gösterir. Örneğin altın çubuğu çizginin sağında ve kırmızıysa, o varlıkta hedeften belirgin şekilde saptığınız — muhtemelen bir kısmını satıp dengeyi yeniden kurmanız gerektiği anlamına gelir." />
      </div>
      <div className="h-[150px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" barCategoryGap={18} margin={{ top: 0, right: 40, left: 0, bottom: 0 }}>
            <XAxis type="number" domain={[0, DOMAIN_MAX]} hide />
            <YAxis
              type="category"
              dataKey="label"
              width={56}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: INK_FAINT }}
            />
            <Tooltip content={<TvTooltip />} cursor={false} />
            <Bar dataKey="actualPct" shape={<ActualBarShape />} barSize={8}>
              {rows.map((row) => (
                <Cell key={row.id} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="m-0 mt-3 text-xs text-ink-faint">Dikey çizgi hedef ağırlığı gösterir. Altın hedefin 7 puan üzerinde.</p>
    </Card>
  );
}
