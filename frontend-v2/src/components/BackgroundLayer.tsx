import React from 'react';
import { createPortal } from 'react-dom';
import { useTheme } from '@/context/ThemeContext';
import gunbatimi from '@/assets/backgrounds/dark-tema-yeni.jpg';

type BackgroundVariant = 'prominent' | 'subtle';

interface BackgroundLayerProps {
  /**
   * 'prominent' -> Dashboard için
   * 'subtle'    -> Portfolio, Risk, Market, AI Chat için
   *
   * Light modda ikisi de aynı değerde (0.65) — tüm sayfalarda tutarlı bir
   * arka plan görünürlüğü için. Bu katmanın kendisi görselin TEK kaynağı:
   * altında (--color-surface) düz beyaz zemin var, ayrı bir "beyaz overlay"
   * div'i yok — düşük opaklık, görselin beyazla harmanlanıp soluklaşması
   * (algısal olarak "beyaz bir tül" etkisi) anlamına geliyor. Görselin daha
   * net görünmesi bu yüzden opaklığı YÜKSELTMEYİ gerektiriyor, düşürmeyi
   * değil. Card.tsx'in şeffaf zemini (bg-white/[0.55]) ile birlikte bu
   * değer, arka planın kartların arasından ve altından net bir renk
   * katmanı olarak sızmasını sağlıyor.
   *
   * Koyu modda variant ayrımı yok — tüm sayfalarda aynı tam ekran tablo
   * (fırtınalı gün batımı manzarası, hiç kırpılmadan/eritilmeden viewport'u
   * dolduruyor) kullanılıyor; header/nav ortak olduğu ve varlık sınıfı
   * renkleri sayfalar arasında paylaşıldığı için tutarlılık token/asset
   * katmanında (bkz. src/index.css .dark, src/data/assetColors.ts) sağlanıyor.
   */
  variant?: BackgroundVariant;
  className?: string;
}

const OPACITY_MAP: Record<BackgroundVariant, string> = {
  prominent: 'opacity-[0.65]',
  subtle: 'opacity-[0.65]',
};

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
 * document.body'ye PORTALLANIYOR: JSX'teki konumu yukarıdaki gibi görünse de
 * (App.tsx'te DashboardEnterFade → "min-h-screen bg-surface" div'inin içinde
 * mount edilir), gerçek DOM'da her zaman body'nin doğrudan altına taşınır.
 * Sebebi: DashboardEnterFade bir framer-motion `motion.div` — opacity
 * animasyonu için transform/will-change ekleyebiliyor, bu da position:fixed
 * için VIEWPORT yerine o motion.div'i containing block yapabiliyor. Sonuç,
 * ekranda simetrik sol/sağ boşluklar olarak görülüyordu (katman viewport'a
 * değil, o ata elemente göre sabitleniyordu). Portal bu ihtimali tamamen
 * ortadan kaldırır — App.tsx'teki hiçbir sarmalayıcının padding/max-width/
 * transform'u katmana miras kalmaz.
 *
 * z-index BİLEREK -z-10 DEĞİL, z-0: "min-h-screen bg-surface" div'i OPAK bir
 * zemin rengi taşıyor (--color-surface) ve pozisyonsuz (position: static),
 * yani negatif z-index bu katmanı o opak rengin ARKASINA gömüp gizlerdi.
 * z-0, App.tsx'teki main'in (z-[1]) ve Header'ın (z-[100]) altında ama
 * bg-surface'in üstünde kalmasını sağlıyor — eskiden "ilk child olmak"
 * bunu DOM sırasıyla garanti ediyordu, portal sonrası bunu z-index üstleniyor.
 *
 * Görsel: fırtınalı bir gün batımı denizcilik tablosu (`dark-tema-yeni.jpg`).
 * KAYNAĞI/LİSANSI DOĞRULANMADI ve dosya OPTİMİZE EDİLMEDİ (~1,8MB) — önceki
 * görsel (`gunbatimi.jpg`, kamu malı, ~410KB'a optimize edilmişti) bilerek
 * yerinde bırakıldı, kullanılmıyor.
 */
export const BackgroundLayer: React.FC<BackgroundLayerProps> = ({
  variant = 'subtle',
  className = '',
}) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  // scale-105: portal + inset-0/inset-x-0 sol/sağda ince boşluğu tam
  // kapatmadı (muhtemelen tarayıcının cover hesabındaki alt-piksel
  // yuvarlaması, ekranın gerçek DPR'ına göre değişiyor). Kesin çözüm için
  // görseli kutudan %5 taşıracak kadar büyütüp merkezden ölçeklemek —
  // hangi kenarda kaç piksellik fark olursa olsun yutuyor. `html` zaten
  // `overflow-x: hidden` (bkz. index.css) o taşan payı yatay scrollbar
  // yaratmadan kırpıyor.
  const content = isDark ? (
    <>
      {/* Tablo artık tüm ekranı (fixed inset-0) kaplıyor — eskiden yalnızca
          üst ~55vh'lik bir bantta durup sayfa zeminine eriyordu, bilerek
          kırptık: artık kırpma/eritme YOK, görsel scroll boyunca aynı
          şekilde viewport'u dolduruyor (light temanın deseniyle aynı). */}
      <div
        aria-hidden="true"
        className={`pointer-events-none fixed inset-0 z-0 h-full w-full origin-center scale-105 bg-cover bg-no-repeat ${className}`}
        style={{
          backgroundImage: `url(${gunbatimi})`,
          backgroundPosition: 'center 68%',
        }}
      />
      {/* Soldan sağa karartma — SADECE sol taraftaki kicker/başlık metninin
          okunabilirliği için. Tüm yükseklik boyunca sabit (görsel artık tam
          ekran olduğu için), sağ/orta hep şeffaf kalıyor. */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-0 h-full w-full"
        style={{
          background:
            'linear-gradient(to right, rgba(10,15,25,0.88) 0%, rgba(10,15,25,0.80) 28%, rgba(10,15,25,0.20) 48%, rgba(10,15,25,0) 62%)',
        }}
      />
    </>
  ) : (
    <div
      aria-hidden="true"
      className={`pointer-events-none fixed inset-0 z-0 h-full w-full origin-center scale-105 bg-cover transition-opacity duration-300 ${OPACITY_MAP[variant]} ${className}`}
      style={{
        backgroundImage: 'url(/backgrounds/vira-background-ship.jpg)',
        backgroundPosition: 'center 40%',
      }}
    />
  );

  return createPortal(content, document.body);
};

export default BackgroundLayer;
