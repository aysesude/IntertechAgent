import { useEffect, useMemo } from "react";
import { Chart } from "react-google-charts";
import type { PerformanceRange, RangeKey } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { computePerformanceStats } from "@/data/mockData";
import { formatTRYCompact, formatPct } from "@/utils/format";
import { BRAND } from "@/utils/colors";
import { useTheme } from "@/context/ThemeContext";

const RANGE_ORDER: RangeKey[] = ["1A", "3A", "6A", "1Y"];

interface PerformanceChartProps {
  /**
   * Gösterilecek seri. İlk açılışta henüz veri yokken `null` olabilir; o
   * durumda kart İSKELET olarak çizilir — kartın kendisi hiçbir zaman
   * DOM'dan kalkmaz, yoksa sayfa düzeni çöker (bkz. DashboardPage).
   */
  range: PerformanceRange | null;
  /** Kullanıcının SEÇTİĞİ dönem. `range` henüz yüklenmemiş olabilir. */
  activeRange: RangeKey;
  onRangeChange: (range: RangeKey) => void;
  /** Yeni dönem yükleniyor: eski seri sönükleştirilerek gösterilmeye devam eder. */
  loading?: boolean;
}

// Google Charts kendi SVG'sini oluştururken options'ı bir kerede işliyor —
// CSS var() string'lerinin bu SVG özniteliklerinde güvenilir şekilde
// çözüldüğü garanti değil, bu yüzden tüm renkler tema değiştikçe burada
// LİTERAL hex olarak yeniden hesaplanıyor (değerler src/index.css'teki
// :root / .dark tanımlarıyla birebir aynı — CSS var'ları kopyalamıyor,
// aynı kaynaktan iki yerde elle senkron tutuyor). Tooltip'in arka planı
// options üzerinden değil, isHtml:true + aşağıdaki index.css kuralıyla
// (.google-visualization-tooltip, gerçek CSS var() içinde) veriliyor.
function buildChartOptions(isDark: boolean) {
  const brandColor = isDark ? "#EB5265" : "#2557E8";
  const gridColor = isDark ? "#2A3B5C" : "#E8E8EC";
  // Light: eski "#A0A5AE" beyaz/yarı saydam kart üstünde ~2.47:1 veriyordu
  // (AA eşiği 4.5:1'in çok altında) — "#6B7180"e çekildi, ~4.9:1. Dark
  // "#9AA4B8" zaten ~5.89:1, dokunulmadı.
  const axisTextColor = isDark ? "#9AA4B8" : "#6B7180";
  const investedLineColor = isDark ? "#4A5A7A" : "#C7CBD4";

  return {
    colors: [brandColor, investedLineColor],
    backgroundColor: "transparent",
    curveType: "function",
    legend: { position: "none" },
    // Sol/sağ 8->16, alt 24->32 — ay isimleri kart kenarına yapışmasın.
    chartArea: { left: 16, right: 16, top: 16, bottom: 32 },
    hAxis: {
      textStyle: { color: axisTextColor, fontSize: 11, fontName: "Manrope" },
      gridlines: { color: "transparent" },
      baselineColor: gridColor,
    },
    vAxis: {
      textPosition: "none",
      gridlines: { color: gridColor, count: 4 },
      baselineColor: "transparent",
    },
    series: {
      // areaOpacity 0.16->0.22: Google Charts options üzerinden gradient
      // dolgu vermiyor, düz opaklığı artırarak dolgu biraz daha derinlikli
      // görünüyor (eski Recharts gradient'inin taklidi değil, kasıtlı sade).
      0: { areaOpacity: 0.22, lineWidth: 2.6 },
      1: { areaOpacity: 0, lineWidth: 1.6, lineDashStyle: [5, 5] },
    },
    // focusTarget:"category" + tooltip.trigger:"focus" -> imleç grafiğin
    // herhangi bir yatay konumunda gezerken (tam veri noktasının üstünde
    // olmak zorunda kalmadan) o güne karşılık gelen HER İKİ seriyi (Portföy +
    // Yatırılan) aynı anda gösteren tek bir tooltip açılır.
    focusTarget: "category",
    tooltip: { trigger: "focus", isHtml: true, textStyle: { fontName: "Manrope", fontSize: 12.5 } },
    // Dikey crosshair, imlecin hizasındaki ayı işaretler — renk temaya göre
    // brandColor ile birebir aynı (yukarıda tanımlı), tek kaynaktan.
    crosshair: { trigger: "focus", orientation: "vertical", color: brandColor, opacity: 0.35 },
    fontName: "Manrope",
    // GEÇİŞ ANİMASYONU BİLEREK YOK (`animation` alanı kaldırıldı).
    //
    // Önceden `animation: { duration: 600, easing: "out" }` vardı: amaç
    // dönem değişince alanın yeni şekle akıcı geçmesiydi. Ama Google
    // Charts'ın animasyon motoru satırları İNDEKSE göre eşleştirip
    // interpolasyon yapıyor — DataTable'ın SATIR SAYISI değişmediği sürece
    // sorunsuz. Pencereler arasında satır sayısı/aralığı büyük ölçüde
    // farklı (bkz. price_service.py:resolve_granularity — 1A/3A/6A günlük
    // ~30/90/180 satır, 1Y haftalık ~52 satır): dönem her değiştiğinde satır
    // sayısı da değişiyor, bu da animasyonun ortasında noktaların birden
    // sıçraması/kopması olarak görülüyordu ("dalgalanarak kırılarak" —
    // canlıda doğrulandı, curveType'ı "none" yapmak da düzeltmedi, kök
    // neden eğri matematiği değil satır-sayısı uyuşmazlığıydı). Sabit sayıda
    // noktaya yeniden örnekleme (resample) yapmadan bu animasyon güvenle
    // çalışmıyor; o daha büyük bir değişiklik, şimdilik animasyon kaldırıldı
    // — geçiş anlık oluyor, kırık bir animasyondan kesinlikle daha iyi.
  };
}

export function PerformanceChart({ range, activeRange, onRangeChange, loading = false }: PerformanceChartProps) {
  const stats = range ? computePerformanceStats(range) : null;
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const chartOptions = useMemo(() => buildChartOptions(isDark), [isDark]);
  // useMemo ile sabitlendi: react-google-charts'ın kendi çizim effect'i
  // `props.data` referansını dependency olarak izliyor (node_modules/
  // react-google-charts/dist/index.js) — memoize edilmezse HER render'da
  // yeni bir array oluşur, bu da chart'ı gereksiz yere sürekli yeniden
  // çizip (animasyon/crosshair durumunu bozarak) alakasız render'larda
  // görsel titremeye yol açar.
  const chartData = useMemo(
    () => [
      ["Tarih", "Portföy", "Yatırılan"],
      ...(range?.points ?? []).map((p) => [p.label, p.portfolio, p.invested]),
    ],
    [range]
  );

  // Türkçe binlik ayıracı (EK madde) — DOM seviyesinde uygulanıyor, Google
  // Charts'ın kendi formatlama API'leri ÜZERİNDEN değil. Denenip elenen
  // yollar (hepsi canlı Playwright/console ile doğrulandı):
  //   1) react-google-charts'ın `formatters` prop'u: node_modules/
  //      react-google-charts/dist/index.js -> applyFormatters, for-of
  //      döngüsü içindeki her switch-case dalında `break` yerine `return`
  //      var — dizideki İLK formatter'dan sonra fonksiyon tamamen çıkıyor,
  //      ikinci sütun (BIST 100) hiç formatlanmıyor.
  //   2) chartEvents "ready" + google.visualization.NumberFormat.format():
  //      hiçbir seçenekle (özel ya da varsayılan) getFormattedValue()'yu
  //      değiştirmedi.
  //   3) chartEvents "ready" + kendi arrayToDataTable() ile taze DataTable +
  //      DataTable.setFormattedValue() + chartWrapper.setDataTable()+draw():
  //      hatasız çalıştı (setFormattedValue başarıyla set ediyor) ama YİNE
  //      DE render edilen tooltip'te görünmedi.
  //   Kök neden: focusTarget:"category" + tooltip.trigger:"focus" ile
  //   çizilen tooltip, DataTable'ın formatlanmış değer önbelleğini hiç
  //   okumuyor — içeriği HAM değerden kendi (ABD virgüllü) varsayılan
  //   formatıyla anlık üretiyor. Yani DataTable'ı nasıl değiştirirsem
  //   değiştireyim, "focus" tetiklemeli tooltip'e ulaşan bir yol yok.
  //   Çözüm: tooltip DOM'a eklendiğinde metnini doğrudan yakalayıp
  //   virgülleri noktaya çeviriyoruz — Google'ın iç formatlama
  //   mekanizmasından tamamen bağımsız, garanti çalışan tek yol bu.
  useEffect(() => {
    const reformatTooltip = () => {
      const tooltip = document.querySelector(".google-visualization-tooltip");
      if (!tooltip) return;
      tooltip.querySelectorAll("span").forEach((span) => {
        const text = span.textContent;
        // "2,854,056" gibi ABD binlik ayıraçlı sayıları yakalar; "Portföy:"
        // gibi etiket metinlerinde virgül olmadığı için onlara dokunmaz.
        if (text && /\d,\d{3}/.test(text)) {
          span.textContent = text.replace(/,/g, ".");
        }
      });
    };
    const observer = new MutationObserver(reformatTooltip);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  return (
    <Card className="p-6 pb-3">
      <div className="mb-1.5 flex items-center justify-between">
        <div>
          <h2 className="font-display m-0 mb-1 text-[17px] font-semibold">Portföy Performansı</h2>
          <p className="m-0 text-[13px] text-ink-muted">
            {range?.subtitle ?? "—"} · portföy değeri
            {loading && " · güncelleniyor…"}
            {/* Pencere portföyün ömründen uzunsa backend başlangıcı ilk işleme
                kırpıyor; söylenmezse grafik sanki o dönem boyunca veri varmış
                gibi görünür (docs/API.md). */}
            {range?.truncatedToInception && " · portföy başlangıcından itibaren"}
          </p>
        </div>
        <div className="flex gap-1">
          {RANGE_ORDER.map((key) => (
            <button
              key={key}
              onClick={() => onRangeChange(key)}
              className={
                "rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-colors " +
                (key === activeRange ? "bg-brand text-white" : "border border-line text-ink-muted dark:border-transparent dark:bg-white/5")
              }
            >
              {key}
            </button>
          ))}
        </div>
      </div>

      {/* Yükleme sırasında seri DOM'da kalıp yalnızca sönükleşiyor: kartın
          yüksekliği sabit, düzen oynamıyor ve geçiş ani bir kaybolma yerine
          yumuşak bir soluklaşma oluyor. */}
      <div
        className="h-[270px] w-full transition-opacity duration-300"
        style={{ opacity: loading ? 0.45 : 1 }}
        aria-busy={loading}
      >
        {/* KEY'DE YALNIZCA TEMA VAR, dönem YOK — bilerek.
            Bir ara key'e dönem de eklenmişti: amaç `startup` animasyonunu
            her dönem değişiminde tetiklemekti, ama sonucu grafiğin YENİDEN
            KURULMASI oldu; kullanıcı bunu "grafik siliniyor ve geri
            geliyor" olarak gördü. Dönem artık key'e girmiyor, grafik
            yerinde durup anında yeni şekle geçiyor (animasyon YOK, bkz.
            buildChartOptions — pencereler arası satır sayısı uyuşmazlığı
            yüzünden kaldırıldı).
            Tema değişimi hâlâ remount ediyor: renkler options üzerinden
            geliyor ve yeniden çizim gerektiriyor. */}
        <Chart
          key={resolvedTheme}
          chartType="AreaChart"
          data={chartData}
          options={chartOptions}
          width="100%"
          height="270px"
          legendToggle={false}
          chartEvents={[
            {
              eventName: "error",
              // Google Charts çizim hatalarını sessizce yutmasın diye —
              // bu olmadan hata sadece kartın içine kırmızı bir kutu olarak
              // basılıyor, konsolda hiçbir iz kalmıyordu.
              callback: ({ eventArgs }) => {
                console.error("PerformanceChart (Google Charts) çizim hatası:", eventArgs);
              },
            },
          ]}
        />
      </div>

      <div className="flex gap-5 border-t border-line2 px-0.5 pb-3.5 pt-3.5 dark:border-transparent">
        <div className="flex items-center gap-2 text-[12.5px] text-ink-muted">
          {/* Koyu temada buildChartOptions'taki brandColor (#EB5265, brand-bright)
              ile birebir aynı literal değer — bg-brand (düz brand, #C4485A)
              burada çizgiyle eşleşmediği için dark: override var. */}
          <span className="h-[2.6px] w-4 rounded-sm bg-brand dark:bg-[#EB5265]" />
          Portföyün
        </div>
        <div className="flex items-center gap-2 text-[12.5px] text-ink-muted">
          {/* buildChartOptions'taki investedLineColor ile birebir aynı literal
              değerler — biri değişirse diğeri de güncellenmeli. */}
          <span className="h-0.5 w-4 rounded-sm" style={{ backgroundColor: isDark ? "#4A5A7A" : "#C7CBD4" }} />
          Yatırılan tutar
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatBlock label="En Yüksek" value={stats ? formatTRYCompact(stats.high) : "—"} />
        <StatBlock label="En Düşük" value={stats ? formatTRYCompact(stats.low) : "—"} />
        {/* Dönem getirisi zaman ağırlıklı (TWR): dönem içinde yatırılan para
            "kâr" olarak görünmesin diye. Yeterli veri yoksa backend null
            döndürüyor ve burada "—" gösteriliyor, 0 değil. */}
        <StatBlock
          label="Dönem Getirisi"
          value={stats?.returnPct == null ? "—" : formatPct(stats.returnPct, 1)}
          color={BRAND}
        />
        <StatBlock label="Toplam Kâr" value={stats ? formatTRYCompact(stats.profit) : "—"} color={BRAND} />
      </div>
    </Card>
  );
}

function StatBlock({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-[10px] border border-line px-4 py-3.5 dark:border-transparent dark:bg-white/5">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[.4px] text-ink-faint">{label}</div>
      <div className="font-display text-[19px] font-bold tracking-[-0.4px]" style={{ color }}>
        {value}
      </div>
    </div>
  );
}
