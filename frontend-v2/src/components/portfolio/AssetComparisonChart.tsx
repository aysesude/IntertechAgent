import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { INK_FAINT, LINE2, FIXED_DARK_CHIP } from "@/utils/colors";
import type { ApiWindow } from "@/api/portfolio";
import { benchmarkUyarisi, toBenchmarkBars, type BenchmarkBar } from "@/adapters/benchmark";
import { useBenchmarkData } from "@/hooks/useBenchmarkData";

/**
 * VİRA — Varlıklar Arası Karşılaştırmalı Getiri grafiği.
 *
 * "Seçili dönemde portföyüm mü, BIST mi, dolar mı, euro mu, altın mı daha çok
 * kazandırdı?" sorusunu cevaplıyor.
 *
 * Yöntem: zaman serisi/endeksleme YOK — her enstrüman için dönem başı ile
 * bugün arasındaki TOPLAM % getiri tek bir çubukla gösteriliyor.
 *
 * VERİ GERÇEK. Bu bileşen daha önce seed'li bir rastgele yürüyüşle SENTETİK
 * getiri üretiyordu (`generateReturns`); artık `/api/portfolio/{id}/benchmark`
 * ucundan geliyor. O uç pencere başındaki miktarları DONDURUYOR ve yalnızca
 * fiyat değişimini ölçüyor — endeks de saf fiyat getirisi olduğu için ancak
 * böyle aynı ölçekte oluyorlar. Yoksa "portföyüm endeksi yendi" cümlesi,
 * aslında sadece dönem içinde yeni para yatırıldığı anlamına gelirdi.
 *
 * Dönem seçenekleri backend penceresine BİREBİR eşleniyor; arayüzde
 * hesaplanan bir tarih aritmetiği yok (eskiden vardı ve sentetik veriyi
 * besliyordu). "Yılbaşından" için backend'e `ytd` penceresi eklendi —
 * diğerlerinin aksine sabit uzunlukta değil, 1 Ocak'tan bugüne.
 */

type Period = ApiWindow;

const PERIOD_LABELS: Record<Period, string> = {
  "1m": "1 Aylık",
  "3m": "3 Aylık",
  "6m": "6 Aylık",
  "12m": "Yıllık",
  ytd: "Yılbaşından",
};

const PERIOD_ORDER: Period[] = ["1m", "3m", "6m", "12m", "ytd"];

/** "+%18,4" / "-%3,2" biçiminde Türkçe yerelleştirilmiş getiri metni. */
function formatReturnTr(value: number | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value).toFixed(1).replace(".", ",");
  return `${sign}%${abs}`;
}

function ComparisonTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point: BenchmarkBar = payload[0].payload;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs text-white shadow-pop"
      style={{ backgroundColor: FIXED_DARK_CHIP }}
    >
      <div className="mb-1 flex items-center gap-1.5 font-semibold">
        <span className="h-2 w-2 rounded-full" style={{ background: point.color }} />
        {point.label}
      </div>
      <span className="font-semibold">{formatReturnTr(point.returnPct)}</span>
    </div>
  );
}

interface AssetComparisonChartProps {
  /**
   * 'nested'     -> başka bir kartın İÇİNE ek bölüm olarak eklenirken
   * 'standalone' -> kendi başına tam bir Card'ın içeriği olarak
   */
  variant?: "nested" | "standalone";
  defaultPeriod?: Period;
}

export function AssetComparisonChart({
  variant = "standalone",
  defaultPeriod = "12m",
}: AssetComparisonChartProps) {
  const [period, setPeriod] = useState<Period>(defaultPeriod);
  const { data, loading, periodLoading, error } = useBenchmarkData(period);

  const bars = data ? toBenchmarkBars(data) : [];
  const uyari = data ? benchmarkUyarisi(data) : null;

  return (
    <div
      className={variant === "nested" ? "mt-5 border-t border-line pt-5 dark:border-transparent" : ""}
    >
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display m-0 text-[15px] font-semibold">
          Varlıklar Arası Karşılaştırmalı Getiri
        </h3>
        <div className="flex flex-wrap gap-1">
          {PERIOD_ORDER.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              disabled={periodLoading}
              className={
                "rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-colors disabled:opacity-60 " +
                (p === period
                  ? "bg-brand text-white"
                  : "border border-line text-ink-muted dark:border-transparent dark:bg-white/5")
              }
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>
      <p className="m-0 mb-1 text-xs text-ink-faint">
        Endeksleme yok — seçili dönemin başı ile bugün arasındaki toplam % getiri, her enstrüman
        için tek bir çubukla doğrudan kıyaslanıyor. Dönem içindeki alım/satım hesaba katılmaz;
        yalnızca fiyat değişimi ölçülür.
      </p>
      {uyari && <p className="m-0 mb-3 text-xs font-medium text-ink-soft">{uyari}</p>}
      {error && <p className="m-0 mb-3 text-xs font-semibold text-negative">{error}</p>}

      <div className="h-[240px] w-full min-w-0">
        {bars.length === 0 ? (
          // Veri yokken UYDURMA çubuk çizilmez (AK 5.5). Kartın yüksekliği
          // korunuyor ki yükleme bitince sayfa zıplamasın.
          <div className="flex h-full items-center justify-center text-sm text-ink-faint">
            {loading ? "Kıyaslama hesaplanıyor…" : "Bu dönem için kıyaslama verisi yok."}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bars} margin={{ top: 20, right: 8, left: -20, bottom: 0 }} barCategoryGap="26%">
              <CartesianGrid stroke={LINE2} vertical={false} />
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10.5, fill: INK_FAINT }}
                interval={0}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: INK_FAINT }}
                tickFormatter={(v) => `${v}%`}
                width={40}
              />
              <Tooltip content={<ComparisonTooltip />} cursor={{ fill: LINE2 }} />
              <Bar dataKey="returnPct" radius={[6, 6, 0, 0]} maxBarSize={56}>
                {bars.map((entry) => (
                  <Cell key={entry.id} fill={entry.color} />
                ))}
                <LabelList
                  dataKey="returnPct"
                  position="top"
                  formatter={formatReturnTr}
                  style={{ fontSize: 11, fontWeight: 600, fill: "#41454C" }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default AssetComparisonChart;
