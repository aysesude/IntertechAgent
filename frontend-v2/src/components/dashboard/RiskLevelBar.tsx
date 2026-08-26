/**
 * 1-7 risk kademesi göstergesi — bankacılık uygulamalarındaki fon risk
 * çubuğunun karşılığı (İş Bankası "Risk Seviyesi" barı örnek alındı).
 *
 * Çubuk YEDİ kademeliktir ve dolan kısım kademeyle orantılıdır. Renk şeridi
 * çubuğun TAMAMINA yayılır, dolan kısma sıkıştırılmaz: 3. kademe her zaman
 * aynı sarıyı gösterir, kademe kaç olursa olsun. Şerit dolan parçaya
 * sığdırılsaydı 1. kademe de 7. kademe de kendi içinde yeşilden kırmızıya
 * giderdi ve renk hiçbir şey anlatmazdı.
 *
 * Ölçek `risk_level` alanının ta kendisidir (`very_low` … `very_high`), yani
 * portföyün ÖLÇÜLEN yıllık oynaklığından gelir — anket puanı ya da dört
 * kademeli `risk_profile` değil. Üçü de bu projede 1-7 ya da benzeri
 * ölçeklerde yaşadığı için karıştırılmaya çok müsait; bkz.
 * `docs/notes/analiste-kapsam-sapmalari.md` §7.
 */

export const RISK_SCALE_MAX = 7;

/**
 * Kademe renkleri (1 → 7). Yeşilden kırmızıya tek yönlü bir rampa; ara
 * tonlar bilerek doygun tutuldu, aksi halde 3-4-5 birbirinden ayrılmıyor.
 *
 * Tema değişkenine bağlanmadılar: risk rampası iki temada da AYNI kalmalı,
 * "kırmızı = yüksek risk" evrensel bir okuma ve temayla kaymamalı (aynı
 * gerekçe `utils/colors.ts` içindeki DANGER için de yazılı).
 */
export const LEVEL_COLORS = [
  "#14A44D",
  "#5FBF3B",
  "#A9C63C",
  "#F0B429",
  "#EE8B29",
  "#E2563D",
  "#D6212B",
] as const;

const GRADIENT = `linear-gradient(90deg, ${LEVEL_COLORS.map(
  (renk, i) => `${renk} ${(i / (RISK_SCALE_MAX - 1)) * 100}%`,
).join(", ")})`;

interface RiskLevelBarProps {
  /** 1-7. `null` ise çubuk çizilmez — risk hesaplanamamıştır (AK 2.7). */
  level: number | null;
}

export function RiskLevelBar({ level }: RiskLevelBarProps) {
  if (level == null) return null;

  const kademe = Math.min(Math.max(Math.round(level), 1), RISK_SCALE_MAX);
  const doluYuzde = (kademe / RISK_SCALE_MAX) * 100;
  // Şerit çubuğun tamamına yayılsın diye iç katman, dolan parçaya göre
  // ters oranda genişletiliyor (7/kademe kat). Bkz. dosya başlığı.
  const seritYuzde = (RISK_SCALE_MAX / kademe) * 100;

  return (
    <div
      className="mt-3 flex items-center gap-2"
      role="img"
      aria-label={`Risk kademesi ${RISK_SCALE_MAX} üzerinden ${kademe}`}
    >
      <div className="h-[7px] flex-1 overflow-hidden rounded-full bg-line2">
        <div className="h-full overflow-hidden rounded-full" style={{ width: `${doluYuzde}%` }}>
          <div className="h-full" style={{ width: `${seritYuzde}%`, background: GRADIENT }} />
        </div>
      </div>
      <span
        className="font-display min-w-[14px] text-right text-[15px] font-bold leading-none"
        style={{ color: LEVEL_COLORS[kademe - 1] }}
      >
        {kademe}
      </span>
    </div>
  );
}
