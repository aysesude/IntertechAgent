import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BRAND, DANGER, INK_FAINT, LINE2, FIXED_DARK_CHIP } from "@/utils/colors";

/**
 * VİRA — Varlıklar Arası Karşılaştırmalı Getiri grafiği.
 *
 * "Seçili dönemde altın mı, dolar mı, euro mu daha çok kazandırdı?"
 * sorusunu cevaplıyor.
 *
 * Yöntem: zaman serisi/endeksleme YOK — her varlık için dönem başı ile bugün
 * arasındaki TOPLAM % getiri tek bir çubukla gösteriliyor (bkz. referans:
 * "Getiri Kıyaslama" bölümü). İncelenen fon kırmızı (danger) renkte
 * vurgulanıyor, diğer dört karşılaştırma enstrümanı (BIST100, USD, EUR,
 * Altın) aynı mavi (brand) tonunda çiziliyor.
 *
 * DÖNEM SEÇİCİ: "Performans Trendi" kartındaki (PerformanceChart.tsx)
 * 1H/1A/3A/6A/1Y mantığına benzer şekilde, gerçek Date aritmetiğine dayalı
 * "bugünden geriye doğru X gün" hesaplaması kullanılıyor; sadece dönemin
 * BAŞLANGIÇ ve BİTİŞ noktaları arasındaki toplam getiri hesaplanıyor:
 *   1 Aylık      -> son 30 gün
 *   3 Aylık      -> son 84 gün
 *   6 Aylık      -> son 168 gün
 *   Yıllık       -> son 12 ay
 *   Yılbaşından  -> 1 Ocak'tan bugüne (gün sayısı yılın ayına göre değişken)
 *
 * ÖNEMLİ: Aşağıdaki veri üretim fonksiyonu (generateReturns) ÖRNEK/
 * PLACEHOLDER'dır — seed'li bir rastgele yürüyüşle sentetik bir dönem-sonu
 * getiri üretiyor. Gerçek entegrasyonda bunun yerine API'den gelen tarihsel
 * fiyat verisinden hesaplanan gerçek dönem getirisi kullanılmalı; veri şekli
 * (her enstrüman için tek bir { id, label, returnPct }) aynı kalacak şekilde
 * tasarlandı.
 */

export interface AssetDefinition {
  id: string;
  label: string;
  color: string;
  /** Yıllık ortalama getiri varsayımı (sentetik veri üretimi için) */
  annualDriftPct: number;
  /** Oynaklık varsayımı (sentetik veri üretimi için) */
  volatility: number;
}

export interface AssetReturn extends AssetDefinition {
  /** Seçili dönem başı ile bugün arasındaki toplam % getiri */
  returnPct: number;
}

const BRAND_BLUE = BRAND;
const FUND_RED = DANGER;

const DEFAULT_ASSETS: AssetDefinition[] = [
  { id: "portfoy", label: "İncelenen Fon", color: FUND_RED, annualDriftPct: 26, volatility: 2.8 },
  { id: "bist", label: "BIST100", color: BRAND_BLUE, annualDriftPct: 24, volatility: 4.5 },
  { id: "dolar", label: "USD", color: BRAND_BLUE, annualDriftPct: 11, volatility: 1.3 },
  { id: "euro", label: "EUR", color: BRAND_BLUE, annualDriftPct: 9, volatility: 1.4 },
  { id: "altin", label: "Altın", color: BRAND_BLUE, annualDriftPct: 22, volatility: 2.2 },
];

type Period = "1m" | "3m" | "6m" | "1y" | "ytd";

interface PeriodSpec {
  label: string;
  unit: "day" | "month";
  /** unit "day" için: dönemin toplam gün uzunluğu. "ytd" için yok — bugüne göre hesaplanır. */
  totalDays?: number;
  /** unit "day" için: iki nokta arası gün adımı (rastgele yürüyüşün adım sıklığı). */
  stepDays?: number;
}

const PERIOD_CONFIG: Record<Period, PeriodSpec> = {
  "1m": { label: "1 Aylık", unit: "day", totalDays: 29, stepDays: 1 },
  "3m": { label: "3 Aylık", unit: "day", totalDays: 84, stepDays: 7 },
  "6m": { label: "6 Aylık", unit: "day", totalDays: 168, stepDays: 14 },
  "1y": { label: "Yıllık", unit: "month" },
  ytd: { label: "Yılbaşından", unit: "day", stepDays: 7 },
};

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

/**
 * Dönem için ara noktaların tarihlerini üretir — bugünden geriye doğru,
 * gerçek Date aritmetiğiyle (yıl sınırlarını da doğru şekilde aşarak).
 * Son nokta her zaman "bugün"dür. Sadece rastgele yürüyüşün adımlarını
 * belirlemek için kullanılır; grafikte tek tek çizilmezler.
 */
function buildDatePoints(period: Period): Date[] {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const spec = PERIOD_CONFIG[period];

  if (spec.unit === "month") {
    const points: Date[] = [];
    for (let i = 11; i >= 0; i--) {
      points.push(new Date(now.getFullYear(), now.getMonth() - i, 1));
    }
    return points;
  }

  const totalDays = period === "ytd" ? daysBetween(new Date(now.getFullYear(), 0, 1), now) : spec.totalDays!;
  const stepDays = spec.stepDays!;

  const points: Date[] = [];
  for (let daysAgo = totalDays; daysAgo > 0; daysAgo -= stepDays) {
    const d = new Date(now);
    d.setDate(d.getDate() - daysAgo);
    points.push(d);
  }
  points.push(now); // son nokta her zaman bugün

  return points;
}

// Basit, deterministik (seed'li) sözde-rastgele üreteç — aynı dönem/varlık
// için her render'da aynı sonucu üretir (Math.random gibi her seferinde
// farklı sonuç vermez).
function mulberry32(seed: number) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

/**
 * Her varlık için seçili dönemin başı ile bugün arasındaki toplam % getiriyi
 * hesaplar. İç mekanizma önceki sürümdeki (zaman serisi üreten) rastgele
 * yürüyüşle aynı — sadece ara noktaları döndürmek yerine dönem sonundaki tek
 * kümülatif getiriyi döndürüyor.
 */
function generateReturns(period: Period, assets: AssetDefinition[]): AssetReturn[] {
  const dates = buildDatePoints(period);

  return assets.map((a) => {
    const rng = mulberry32(seedFromString(a.id + period));
    let value = 100;
    dates.forEach((date, i) => {
      if (i === 0) return;
      const stepDays = daysBetween(dates[i - 1], date);
      const periodDriftPct = (a.annualDriftPct * stepDays) / 365;
      const noise = (rng() - 0.5) * 2 * a.volatility;
      value = Math.max(40, value * (1 + (periodDriftPct + noise) / 100));
    });
    return { ...a, returnPct: Math.round((value - 100) * 10) / 10 };
  });
}

/** "+%18,4" / "-%3,2" biçiminde Türkçe yerelleştirilmiş getiri metni. */
function formatReturnTr(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value).toFixed(1).replace(".", ",");
  return `${sign}%${abs}`;
}

function ComparisonTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point: AssetReturn = payload[0].payload;
  return (
    <div className="rounded-lg px-3 py-2 text-xs text-white shadow-pop" style={{ backgroundColor: FIXED_DARK_CHIP }}>
      <div className="mb-1 flex items-center gap-1.5 font-semibold">
        <span className="h-2 w-2 rounded-full" style={{ background: point.color }} />
        {point.label}
      </div>
      <span className="font-semibold">{formatReturnTr(point.returnPct)}</span>
    </div>
  );
}

interface AssetComparisonChartProps {
  assets?: AssetDefinition[];
  /**
   * 'nested'     -> başka bir kartın İÇİNE ek bölüm olarak eklenirken
   * 'standalone' -> kendi başına tam bir Card'ın içeriği olarak
   */
  variant?: "nested" | "standalone";
  defaultPeriod?: Period;
}

export function AssetComparisonChart({
  assets = DEFAULT_ASSETS,
  variant = "standalone",
  defaultPeriod = "1y",
}: AssetComparisonChartProps) {
  const [period, setPeriod] = useState<Period>(defaultPeriod);

  const data = useMemo(() => generateReturns(period, assets), [period, assets]);

  return (
    <div className={variant === "nested" ? "mt-5 border-t border-line pt-5 dark:border-transparent" : ""}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display m-0 text-[15px] font-semibold">Varlıklar Arası Karşılaştırmalı Getiri</h3>
        <div className="flex flex-wrap gap-1">
          {(Object.keys(PERIOD_CONFIG) as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={
                "rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-colors " +
                (p === period ? "bg-brand text-white" : "border border-line text-ink-muted dark:border-transparent dark:bg-white/5")
              }
            >
              {PERIOD_CONFIG[p].label}
            </button>
          ))}
        </div>
      </div>
      <p className="m-0 mb-4 text-xs text-ink-faint">
        Endeksleme yok — seçili dönemin başı ile bugün arasındaki toplam % getiri, her enstrüman için tek bir
        çubukla doğrudan kıyaslanıyor. İncelenen fon vurgulu, diğer enstrümanlar kıyas amaçlı gösteriliyor.
      </p>

      <div className="h-[240px] w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 20, right: 8, left: -20, bottom: 0 }} barCategoryGap="26%">
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
              {data.map((entry) => (
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
      </div>
    </div>
  );
}

export default AssetComparisonChart;
