import React from 'react';
import { motion, useReducedMotion, type Variants } from 'framer-motion';
import { INTRO_TIMING } from './LoginScreen';

/**
 * Sayfa geçişi.
 *
 * ÖNCEKİ SÜRÜM KALDIRILDI. Geçiş, tüm ekranı kaplayan bir SVG "sıvı dalga"
 * efektiydi: altı animasyonlu daire, üzerlerinde `feGaussianBlur` +
 * `feColorMatrix` ("goo" tekniği) ve ekranı kaplayan bir gradyan katman.
 * Her sayfa değişiminde bu filtre her karede yeniden hesaplanıyordu —
 * SVG filtreleri GPU'da compose edilmez, pahalıdır ve efekt tam ekran
 * olduğu için maliyet ekran boyutuyla büyüyordu. Görsel kazancı, her
 * gezinmede eklediği yükü ve ~1,1 saniyelik gecikmeyi karşılamıyordu.
 *
 * Yerine yalnızca `opacity` + küçük bir `translateY` var: ikisi de
 * compositor'da işlenir, düzen (layout) hesabı tetiklemez ve pratikte
 * bedavaya yakındır. Geçiş de belirgin şekilde kısaldı (~1,1 sn → ~0,3 sn),
 * yani gezinme hızlandı.
 */

/** İçeriğin belirme süresi. */
const ENTER_DURATION_S = 0.28;
/** Çıkış, girişten kısa: `AnimatePresence mode="wait"` ikisini ARDIŞIK oynatıyor. */
const EXIT_DURATION_S = 0.16;

const contentVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: ENTER_DURATION_S, ease: 'easeOut' },
  },
  exit: {
    opacity: 0,
    y: -6,
    transition: { duration: EXIT_DURATION_S, ease: 'easeIn' },
  },
};

/**
 * "dashboardEnter" fazı — LoginScreen'in Faz 5'i: giriş sonrası Dashboard ilk
 * kez mount olduğunda finans kartları ve grafik sırayla belirir.
 *
 * Dalga kalktığı için buradaki gecikme de neredeyse sıfıra indi: eskiden
 * içeriğin görünmesi için kaplayan katmanın çekilmesini beklemek gerekiyordu.
 */
const DASHBOARD_REVEAL_DELAY_S = 0.08;
const DASHBOARD_STAGGER_GAP_S = INTRO_TIMING.dashboardCardStaggerMs / 1000;
const DASHBOARD_ITEM_DURATION_S = 0.35;
/** 4 finans kartı + performans grafiği satırı — DashboardPage'deki StaggerItem sayısıyla aynı kalmalı. */
const DASHBOARD_ITEM_COUNT = 5;

const dashboardContentVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: {
      delay: DASHBOARD_REVEAL_DELAY_S,
      duration: ENTER_DURATION_S,
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

/**
 * İçeriğin GÖRÜNÜR olmaya başladığı an (ms).
 *
 * Mount anında bir şey animasyonlanacaksa (ör. RiskGauge'un sayaç
 * animasyonu) bu değer kadar beklemesi gerekir, yoksa kullanıcı henüz
 * görmeden oynayıp biter. Dalga kaldığı sürece bu ~605 ms'ydi; artık
 * içerik hemen belirmeye başlıyor.
 */
export const CONTENT_REVEAL_DELAY_MS = 80;

interface PageTransitionProps {
  children: React.ReactNode;
  /** Sadece LoginScreen'den gelen ilk Dashboard mount'unda true — Faz 5. */
  dashboardEnter?: boolean;
}

export const PageTransition: React.FC<PageTransitionProps> = ({ children, dashboardEnter = false }) => {
  const shouldReduceMotion = useReducedMotion();
  const useStagger = dashboardEnter && !shouldReduceMotion;

  // Hareketi azaltma tercihinde hiç animasyon yok: içerik doğrudan görünür.
  if (shouldReduceMotion) {
    return <div className="relative min-h-screen">{children}</div>;
  }

  return (
    <motion.div
      initial="initial"
      animate="animate"
      exit="exit"
      variants={useStagger ? dashboardContentVariants : contentVariants}
      className="relative min-h-screen"
    >
      {children}
    </motion.div>
  );
};

/**
 * LoginScreen → Dashboard el değişimi (Faz 4 → 5).
 *
 * App.tsx eskiden `if (!authenticated) return <LoginScreen/>` ile sert bir
 * unmount/mount yapıyordu — LoginScreen'in son karesi ile Dashboard'un ilk
 * karesi arasında boş/beyaz bir kare görünüyordu.
 *
 * Çözüm: App.tsx LoginScreen'i bu bileşenle sarmalayıp AnimatePresence içinde
 * tutuyor (authenticated true olunca "exit" olur, INTRO_TIMING.loginHandoffMs
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
