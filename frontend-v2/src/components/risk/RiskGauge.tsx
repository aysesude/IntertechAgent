import { useEffect, useState, type MouseEvent } from "react";
import { motion } from "framer-motion";
import { Card } from "@/components/common/Card";
import { CONTENT_REVEAL_DELAY_MS } from "@/components/PageTransition";
import { useCountUp, easeOutCubic } from "@/hooks/useCountUp";
import { BRAND, DANGER, INK_FAINT, LINE2, SURFACE_ELEVATED, FIXED_DARK_CHIP } from "@/utils/colors";

interface RiskGaugeProps {
  score: number;
  label: string;
  description: string;
}

const CENTER_X = 150;
const CENTER_Y = 160;
const RADIUS = 120;
const NEAR_THRESHOLD = 3;

// Gauge'un sayaç animasyonu mount anında değil, içerik gerçekten görünür
// olmaya başladığında tetiklenmeli — yoksa kimse görmeden oynayıp biter.
//
// Değer artık PageTransition'dan İTHAL EDİLİYOR, elle kopyalanmıyor: eskiden
// burada 620 sabiti vardı ve "PageTransition'daki gecikme değişirse burası da
// güncellenmeli" notu düşülmüştü. Nitekim değişti (tam ekran dalga geçişi
// kaldırıldı, gecikme ~605 ms'den ~80 ms'ye indi) — tek kaynağa bağlamak bu
// senkronu elle takip etme yükünü ortadan kaldırıyor.

function dotColorAt(value: number): string {
  const t = value / 100;
  const stops: [number, [number, number, number]][] = [
    [0, [143, 180, 242]],
    [0.5, [30, 95, 217]],
    [1, [230, 57, 70]],
  ];
  let a = stops[0];
  let b = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (t >= stops[i][0] && t <= stops[i + 1][0]) {
      a = stops[i];
      b = stops[i + 1];
      break;
    }
  }
  const span = b[0] - a[0] || 1;
  const lt = (t - a[0]) / span;
  const mix = a[1].map((c, i) => Math.round(c + (b[1][i] - c) * lt));
  return `rgb(${mix.join(",")})`;
}

function gaugePoint(value: number) {
  const angleDeg = 180 - value * 1.8;
  const rad = (angleDeg * Math.PI) / 180;
  return {
    x: CENTER_X + RADIUS * Math.cos(rad),
    y: CENTER_Y - RADIUS * Math.sin(rad),
  };
}

export function RiskGauge({ score, label, description }: RiskGaugeProps) {
  // Sayfa geçişi bittiğinde (içerik görünür olduğunda) true olur; skala
  // animasyonu ancak o zaman gerçek score'a doğru saymaya başlar.
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    setRevealed(false);
    const timer = setTimeout(() => setRevealed(true), CONTENT_REVEAL_DELAY_MS);
    return () => clearTimeout(timer);
  }, [score]);

  const animatedScore = useCountUp(revealed ? score : 0, 0, 800, easeOutCubic);
  const [hoverValue, setHoverValue] = useState<number | null>(null);

  const needle = gaugePoint(animatedScore);
  const dotColor = dotColorAt(animatedScore);

  const handleGaugeMove = (e: MouseEvent<SVGPathElement>) => {
    const svg = e.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (300 / rect.width);
    const my = (e.clientY - rect.top) * (200 / rect.height);
    const dx = mx - CENTER_X;
    const dy = CENTER_Y - my;
    let angle = (Math.atan2(dy, dx) * 180) / Math.PI;
    if (angle < 0) angle += 360;
    const value = Math.max(0, Math.min(100, (180 - angle) / 1.8));
    setHoverValue(value);
  };

  const isHovering = hoverValue != null;
  const isNear = isHovering && Math.abs(hoverValue - score) <= NEAR_THRESHOLD;
  // Hover olmadığında da geçerli bir konum tutulur (needle'ın üstünde, görünmez
  // halde) — böylece tooltip component'i hiç unmount/remount olmaz, sadece
  // opacity/scale ile gösterilir ya da gizlenir.
  const tooltipPoint = isHovering ? gaugePoint(hoverValue) : needle;
  const hoverColor = isHovering ? dotColorAt(hoverValue) : BRAND;

  return (
    <Card className="animate-fadeUp relative overflow-visible p-6 pt-7">
      <h2 className="font-display m-0 mb-0.5 text-[17px] font-semibold">Risk Profili</h2>
      <p className="m-0 text-[13px] text-ink-faint">Ölçek: Korumacı → Agresif</p>
      <div className="relative mt-1.5">
        <svg viewBox="0 0 300 200" className="block w-full overflow-visible">
          <defs>
            <linearGradient id="gaugeGrad" x1="30" y1="160" x2="270" y2="160" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#8FB4F2" />
              <stop offset="50%" stopColor={BRAND} />
              <stop offset="100%" stopColor={DANGER} />
            </linearGradient>
          </defs>
          <path d="M30,160 A120,120 0 0 1 270,160" fill="none" stroke={LINE2} strokeWidth={10} strokeLinecap="round" />
          <path d="M30,160 A120,120 0 0 1 270,160" fill="none" stroke="url(#gaugeGrad)" strokeWidth={10} strokeLinecap="round" />
          <path
            d="M30,160 A120,120 0 0 1 270,160"
            fill="none"
            stroke="transparent"
            strokeWidth={40}
            style={{ cursor: "crosshair" }}
            onMouseMove={handleGaugeMove}
            onMouseLeave={() => setHoverValue(null)}
          />
          <circle
            cx={needle.x}
            cy={needle.y}
            r={11}
            fill={dotColor}
            style={{ filter: `drop-shadow(0 0 5px ${dotColor})`, pointerEvents: "none" }}
          />
          <circle cx={needle.x} cy={needle.y} r={11} fill="none" stroke={SURFACE_ELEVATED} strokeWidth={3} style={{ pointerEvents: "none" }} />
          {isHovering && (
            <circle cx={tooltipPoint.x} cy={tooltipPoint.y} r={3.5} fill={hoverColor} style={{ pointerEvents: "none" }} />
          )}
          <g fontFamily="Manrope" fontSize={11} fill={INK_FAINT}>
            <text x="18" y="182">0</text>
            <text x="266" y="182">100</text>
          </g>
        </svg>

        {/*
          Tooltip her zaman mount edilir; görünürlük ve "yakın nokta" büyümesi
          sadece animate prop'undaki opacity/scale değerleriyle kontrol edilir.
          AnimatePresence / conditional mount kullanılmıyor, bu yüzden component
          hover sırasında hiçbir zaman unmount/remount olmuyor (flicker yok).
        */}
        <motion.div
          initial={false}
          animate={{ opacity: isHovering ? 1 : 0, scale: isNear ? 1.14 : 1 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className="pointer-events-none absolute z-50 flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[12.5px] font-semibold text-white shadow-pop"
          style={{
            backgroundColor: FIXED_DARK_CHIP,
            left: `${(tooltipPoint.x / 300) * 100}%`,
            top: `${(tooltipPoint.y / 200) * 100}%`,
            // İmleç konumuna göre dinamik hesaplanan nokta üzerinde ortalanıp
            // 14px yukarıda konumlanır; x/y burada framer-motion'ın kendi
            // transform kompozisyonuna dahil edilir (animate.scale ile çakışmaz).
            x: "-50%",
            y: "calc(-100% - 14px)",
          }}
        >
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: hoverColor }} />
          {Math.round(isHovering ? hoverValue : score)}
        </motion.div>
      </div>

      <div className="-mt-1.5 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-brand-border bg-brand-tint px-4 py-2 text-[13px] font-semibold text-brand">
          {label}
        </div>
        <p className="m-0 mt-3.5 text-[13px] leading-[1.6] text-ink-muted">{description}</p>
      </div>
    </Card>
  );
}
