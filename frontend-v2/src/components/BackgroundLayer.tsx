import React from 'react';
import { useTheme } from '@/context/ThemeContext';
import gunbatimi from '@/assets/backgrounds/gunbatimi.jpg';

type BackgroundVariant = 'prominent' | 'subtle';

interface BackgroundLayerProps {
  /**
   * 'prominent' -> Dashboard için
   * 'subtle'    -> Portfolio, Risk, Market, AI Chat için
   *
   * Light modda ikisi de aynı değerde (0.50) — tüm sayfalarda tutarlı bir
   * arka plan saydamlığı için. Card.tsx'in hafifçe saydam olması
   * (bg-white/[0.72], LoginScreen'deki login kartıyla aynı değer) ile
   * birlikte bu değer, arka planın kartların arasından ve altından net
   * bir renk katmanı olarak sızmasını sağlıyor.
   *
   * Koyu modda variant ayrımı yok — tüm sayfalarda aynı üst-bant tablo
   * (gün batımı manzarası) ve aynı gradient eritme kullanılıyor; header/nav
   * ortak olduğu ve varlık sınıfı
   * renkleri sayfalar arasında paylaşıldığı için tutarlılık token/asset
   * katmanında (bkz. src/index.css .dark, src/data/assetColors.ts) sağlanıyor.
   */
  variant?: BackgroundVariant;
  className?: string;
}

const OPACITY_MAP: Record<BackgroundVariant, string> = {
  prominent: 'opacity-[0.50]',
  subtle: 'opacity-[0.50]',
};

// Koyu temada tablo sayfanın üst bandına (yaklaşık 55vh) yerleşiyor ve
// aşağı doğru sayfa zeminine (--color-surface) yumuşak bir gradientle
// eriyor — tüm ekranı kaplayan eski silik doku mantığından kasıtlı olarak
// farklı, burada tablo yüksek görünürlükte.
const DARK_BAND_HEIGHT = '55vh';

/**
 * Sayfa arka planına sabit (fixed) şekilde yerleşen, saydam görsel katmanı.
 * TEK örnek olarak App.tsx'te, AnimatePresence'ın (sayfa geçişleri) DIŞINDA
 * render edilir — sayfalar kendi içinde bunu artık mount etmiyor. Aksi halde
 * mode="wait" her sayfa değişiminde bu katmanı unmount/remount ederdi ve
 * geçiş sırasında arka plan bir an kaybolup yeniden kurulurdu.
 *
 *   <div className="min-h-screen bg-surface">
 *     <BackgroundLayer variant={screen === "dashboard" ? "prominent" : "subtle"} />
 *     <Header ... />
 *     <main> ...AnimatePresence + sayfa içeriği... </main>
 *   </div>
 *
 * Görsel 1918 tarihli bir tablo (kamu malı); ~410KB'a optimize edilmiş
 * hali kullanılıyor, orijinal yüksek çözünürlüklü kopya ayrıca mevcut.
 */
export const BackgroundLayer: React.FC<BackgroundLayerProps> = ({
  variant = 'subtle',
  className = '',
}) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  if (isDark) {
    return (
      <>
        <div
          aria-hidden="true"
          className={`pointer-events-none fixed inset-x-0 top-0 z-0 bg-cover ${className}`}
          style={{
            height: DARK_BAND_HEIGHT,
            backgroundImage: `url(${gunbatimi})`,
            backgroundPosition: 'center 74%',
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-x-0 top-0 z-0"
          style={{
            height: DARK_BAND_HEIGHT,
            // İlk %78 tamamen şeffaf (tablo tam görünür, ay/yansıma kapanmıyor);
            // son %22'de sayfa zeminine (--color-surface) yumuşakça eriyor.
            background:
              'linear-gradient(to bottom, rgba(10,19,29,0) 0%, rgba(10,19,29,0) 78%, var(--color-surface) 100%)',
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-x-0 top-0 z-0"
          style={{
            height: DARK_BAND_HEIGHT,
            // Soldan sağa karartma — dikey erime gradientinin ÜSTÜNE eklenir
            // (yerine geçmez). Bu tablo öncekinden daha parlak turuncu; sol
            // taraftaki kicker/başlık metni bu karartma olmadan güneşin
            // üstünde okunmuyordu. %62'den itibaren tamamen şeffaf kalıyor,
            // güneş ve bulutlar (ekranın ortası) karartılmıyor.
            background:
              'linear-gradient(to right, rgba(10,15,25,0.88) 0%, rgba(10,15,25,0.80) 28%, rgba(10,15,25,0.20) 48%, rgba(10,15,25,0) 62%)',
          }}
        />
      </>
    );
  }

  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none fixed inset-0 z-0 bg-cover bg-center transition-opacity duration-300 ${OPACITY_MAP[variant]} ${className}`}
      style={{ backgroundImage: 'url(/backgrounds/vira-background-ship.jpg)' }}
    />
  );
};

export default BackgroundLayer;
