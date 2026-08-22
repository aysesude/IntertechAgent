import React from 'react';
import { motion, useReducedMotion, type Variants } from 'framer-motion';
import { INTRO_TIMING } from './LoginScreen';
import { useTheme } from '@/context/ThemeContext';

/**
 * VİRA "liquid wave" sayfa geçişi — birbirine kaynaşan sıvı damlacıklar
 * halinde soldan sağa akan, yumuşak pastel renkli bir geçiş efekti.
 *
 * Önceki versiyondan farkı: düz/dalgalı kenarlı bloklar yerine, SVG'nin
 * klasik "goo" (gooey/metaball) filtre tekniğiyle gerçek bir sıvının
 * birleşip akması taklit ediliyor. Birden fazla daire (damlacık) farklı
 * hız ve gecikmelerle soldan sağa hareket ederken, aralarındaki
 * bulanıklaştırma + kontrast filtresi onları görsel olarak "kaynaştırıp"
 * tek bir akışkan kütle gibi gösteriyor.
 *
 * Renk paleti: yumuşak, düşük kontrastlı açık mavi tonlarda gradyan
 * (buz mavisi → VİRA marka mavisinin açık tonu → gök mavisi) — turkuaz/
 * yeşil ton yok, koyu/yoğun değil, akışkan ve sakin.
 *
 * Kurulum: npm install framer-motion
 *
 * Kullanım (React Router v6):
 *   <AnimatePresence mode="wait">
 *     <Routes location={location} key={location.pathname}>
 *       <Route path="/dashboard" element={<PageTransition><Dashboard /></PageTransition>} />
 *       ...
 *     </Routes>
 *   </AnimatePresence>
 *
 * State tabanlı switcher kullanılıyorsa (react-router yoksa), aynı mantığı
 * <AnimatePresence mode="wait"> içinde key={screen} ile kurun.
 */

const SWEEP_DURATION = 1.1;
const EASE: [number, number, number, number] = [0.37, 0, 0.15, 1];

interface Droplet {
  cx: number;
  r: number;
  delay: number;
  durationScale: number;
}

// Damlacıkların yatay konumu, boyutu ve zamanlaması — hafif düzensiz
// (tam senkron değil) olması sıvının organik/gerçekçi akmasını sağlıyor.
const DROPLETS: Droplet[] = [
  { cx: 6, r: 20, delay: 0.02, durationScale: 1.0 },
  { cx: 24, r: 22, delay: 0.07, durationScale: 0.94 },
  { cx: 42, r: 21, delay: 0.0, durationScale: 1.05 },
  { cx: 58, r: 23, delay: 0.09, durationScale: 0.97 },
  { cx: 76, r: 21, delay: 0.04, durationScale: 1.02 },
  { cx: 94, r: 20, delay: 0.06, durationScale: 0.96 },
];

// En büyük damlacığın yarıçapı (23) + blur bulanıklığının görsel taşması
// (stdDeviation 7, ~2.5x yayılım) hesaba katıldığında viewBox kenarından
// (0 / 100) en az ~43 birim uzakta olması gerekiyor, yoksa dairenin veya
// blurunun bir kısmı görünür alanda kalıp iz bırakıyor. -18/118 bunun için
// yetersizdi (118 - 23 = 95, hâlâ 0-100 içinde) — -50/150 tam güvenli marj.
const HIDDEN_TOP = -50;
const HIDDEN_BOTTOM = 150;

const makeDropletVariants = (delay: number, duration: number): Variants => ({
  // Ekranın üstünde, tamamen görünmez halde başlar
  initial: { cy: HIDDEN_TOP },
  // Aşağı doğru süpürülüp ekranın altından tamamen çıkar — ekranda
  // hiçbir kalıntı/leke bırakmadan kaybolur
  animate: {
    cy: HIDDEN_BOTTOM,
    transition: { duration, delay, ease: EASE },
  },
  exit: {
    cy: HIDDEN_TOP,
    transition: { duration, delay: 0, ease: EASE },
  },
});

const contentVariants: Variants = {
  initial: { opacity: 0, scale: 0.995 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: { delay: SWEEP_DURATION * 0.55, duration: 0.5, ease: 'easeOut' },
  },
  exit: {
    opacity: 0,
    scale: 0.995,
    transition: { duration: SWEEP_DURATION * 0.35, ease: 'easeIn' },
  },
};

/**
 * "dashboardEnter" fazı — LoginScreen'in Faz 5'i: giriş sonrası Dashboard
 * ilk kez mount olduğunda, normal contentVariants'ın aynı gecikme/süresini
 * korur (RiskGauge'daki CONTENT_REVEAL_DELAY_MS ile senkron kalması için
 * SWEEP_DURATION * 0.55 dokunulmadı) ama üstüne staggerChildren ekler —
 * böylece DashboardPage'deki finans kartları ve grafik, dashboardStaggerItem
 * variants'ını kullanan çocuklar olarak sırayla belirir.
 */
const DASHBOARD_REVEAL_DELAY_S = SWEEP_DURATION * 0.55;
const DASHBOARD_STAGGER_GAP_S = INTRO_TIMING.dashboardCardStaggerMs / 1000;
const DASHBOARD_ITEM_DURATION_S = 0.35;
/** 4 finans kartı + performans grafiği satırı — DashboardPage'deki StaggerItem sayısıyla aynı kalmalı. */
const DASHBOARD_ITEM_COUNT = 5;

const dashboardContentVariants: Variants = {
  initial: { opacity: 0, scale: 0.995 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: {
      delay: DASHBOARD_REVEAL_DELAY_S,
      duration: 0.5,
      ease: 'easeOut',
      staggerChildren: DASHBOARD_STAGGER_GAP_S,
    },
  },
  exit: contentVariants.exit,
};

/** DashboardPage'de dashboardEnter sırasında tek tek beliren öğeler için. */
export const dashboardStaggerItem: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: DASHBOARD_ITEM_DURATION_S, ease: 'easeOut' } },
};

/**
 * Faz 5'in görsel olarak tamamlanma süresi (App.tsx'te justLoggedIn'i
 * sıfırlamak için kullanılır) — gecikme + stagger + son öğenin süresi.
 * Tek kaynak burası; App.tsx bunu import edip kullanır, kendi hardcoded
 * ms değeri tutmaz.
 */
export const DASHBOARD_ENTER_DURATION_MS = Math.round(
  (DASHBOARD_REVEAL_DELAY_S + (DASHBOARD_ITEM_COUNT - 1) * DASHBOARD_STAGGER_GAP_S + DASHBOARD_ITEM_DURATION_S) * 1000
);

// Damlacıklar arasında ekranın beyaz kalmasını önleyen, sürekli kaplayan
// yumuşak bir temel renk katmanı — damlacıklar bunun üstünde sadece
// dokusal/organik bir detay olarak görünür.
//
// ÖNEMLİ (ölçülerek bulunan bir hata): AnimatePresence mode="wait"
// kullanıldığı için eski sayfa TAMAMEN kaldırılmadan yenisi mount olmuyor.
// Wash'ın exit'te damlacıklardan ÖNCE sıfıra sönmesi ya da enter'da
// damlacıklardan SONRA belirmesi, iki mount arasında ~300ms'lik "hiçbir
// şeyin ekranı kaplamadığı" bir boşluk yaratıyordu (test edilip ölçüldü —
// bkz. rAF tabanlı örnekleme). Çözüm: exit'te wash'ı zaten ulaştığı 0.9
// değerinde SABİT tutuyoruz (hedef mevcut değerle aynı olduğu için görsel
// bir değişiklik olmaz, ama React bu alt-ağacı en yavaş damlacık bitene
// kadar DOM'da tutar) — böylece wash damlacıklardan asla önce kaybolmaz.
// Enter'da ise hızlı yükselip, gerçek sayfa içeriği tamamen görünür
// olana kadar (contentVariants'ın kendi gecikme+süresi tamamlanana kadar)
// solmaya BAŞLAMAZ.
const baseWashVariants: Variants = {
  initial: { opacity: 0 },
  animate: {
    // Çok hızlı (~40ms) doğrusal yükseliş — mount olur olmaz ekran hemen
    // kaplansın. "easeInOut" burada kullanılmıyor çünkü S-eğrisi, kısa bir
    // dilimde bile başlangıcı yavaşlatıp yükselişi geciktiriyordu (ölçülüp
    // görüldü). İçerik görünür hale gelene kadar (bkz. contentVariants:
    // delay 0.55 + 0.5s süre ≈ 1.05×SWEEP_DURATION) uzunca beklet, sonra
    // sönerken tekrar yumuşak "easeInOut" kullan.
    opacity: [0, 0.9, 0.9, 0.9, 0],
    transition: {
      duration: SWEEP_DURATION * 1.45,
      times: [0, 0.025, 0.03, 0.8, 1],
      ease: ['linear', 'linear', 'easeInOut', 'easeInOut'],
    },
  },
  // Zaten ulaşılmış olan 0.9 değerinde sabit kalır — damlacıklar
  // ekrandan tamamen çıkana kadar (component unmount olana kadar) wash
  // hiç solmaz, aniden değil React tarafından temizlenerek kaybolur.
  exit: { opacity: 0.9 },
};

interface PageTransitionProps {
  children: React.ReactNode;
  /** Sadece LoginScreen'den gelen ilk Dashboard mount'unda true — Faz 5. */
  dashboardEnter?: boolean;
}

export const PageTransition: React.FC<PageTransitionProps> = ({ children, dashboardEnter = false }) => {
  const shouldReduceMotion = useReducedMotion();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const useStagger = dashboardEnter && !shouldReduceMotion;

  return (
    <motion.div initial="initial" animate="animate" exit="exit" className="relative min-h-screen">
      <motion.div variants={useStagger ? dashboardContentVariants : contentVariants}>{children}</motion.div>

      <div className="pointer-events-none fixed inset-0 z-[100]" aria-hidden="true">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
          <defs>
            <linearGradient id="vira-liquid-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
              {isDark ? (
                <>
                  <stop offset="0%" stopColor="#4A1520" />
                  <stop offset="50%" stopColor="#6B2231" />
                  <stop offset="100%" stopColor="#521825" />
                </>
              ) : (
                <>
                  <stop offset="0%" stopColor="#DCEEFC" />
                  <stop offset="50%" stopColor="#A9D4F0" />
                  <stop offset="100%" stopColor="#EAF6FE" />
                </>
              )}
            </linearGradient>

            {/* "Goo" filtresi — bulanıklaştır, sonra kontrastı artır.
                Bu ikisi birlikte, üst üste binen daireleri birbirine
                kaynaşmış tek bir sıvı kütle gibi gösterir. */}
            <filter id="vira-goo">
              <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="blur" />
              <feColorMatrix
                in="blur"
                mode="matrix"
                values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 22 -10"
                result="goo"
              />
            </filter>
          </defs>

          {/* Temel katman — her zaman ekranı kaplar, damlacıklar arasında
              beyaz boşluk sızmasını önler */}
          <motion.rect
            x="0"
            y="0"
            width="100"
            height="100"
            fill="url(#vira-liquid-gradient)"
            variants={baseWashVariants}
          />

          <g filter="url(#vira-goo)" fill="url(#vira-liquid-gradient)" opacity={isDark ? 0.92 : 0.85}>
            {DROPLETS.map((d, i) => {
              const variants = makeDropletVariants(d.delay, SWEEP_DURATION * d.durationScale);
              return (
                <motion.circle
                  key={i}
                  cx={d.cx}
                  r={d.r}
                  variants={variants}
                />
              );
            })}
          </g>
        </svg>
      </div>
    </motion.div>
  );
};

/**
 * LoginScreen → Dashboard el değişimi (Faz 4 → 5).
 *
 * App.tsx eskiden `if (!authenticated) return <LoginScreen/>` ile sert bir
 * unmount/mount yapıyordu — LoginScreen'in son karesi ile Dashboard'un ilk
 * karesi arasında (Dashboard'un kendi mount süresi + PageTransition'ın wash
 * animasyonunun ilk birkaç frame'i) boş/beyaz bir kare görünüyordu.
 *
 * Çözüm: App.tsx artık LoginScreen'i bu bileşenle sarmalayıp AnimatePresence
 * içinde tutuyor (authenticated true olunca "exit" olur, INTRO_TIMING.loginHandoffMs
 * boyunca fade-out olarak DOM'da kalır) ve aynı anda authenticated ağacını
 * DashboardEnterFade ile fade-in ediyor — ikisi aynı süre boyunca üst üste
 * (crossfade) render olur, aralarında boş kare kalmaz.
 */
const HANDOFF_TRANSITION = { duration: INTRO_TIMING.loginHandoffMs / 1000, ease: 'easeInOut' as const };

export const LoginExitOverlay: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const shouldReduceMotion = useReducedMotion();
  return (
    <motion.div
      className="fixed inset-0 z-[200]"
      exit={{ opacity: 0 }}
      transition={shouldReduceMotion ? { duration: 0 } : HANDOFF_TRANSITION}
    >
      {children}
    </motion.div>
  );
};

export const DashboardEnterFade: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const shouldReduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={shouldReduceMotion ? { duration: 0 } : HANDOFF_TRANSITION}
    >
      {children}
    </motion.div>
  );
};

export default PageTransition;
