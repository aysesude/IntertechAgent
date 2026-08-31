import { useEffect } from "react";

/**
 * Modal açıkken arkadaki sayfayı KİLİTLER — `body.style.overflow = "hidden"`
 * DEĞİL: iOS Safari'de bu, touch/trackpad ile yapılan "rubber-band" (lastik
 * gibi taşma) kaydırmasını engellemiyor; body görünmez şekilde kaymaya devam
 * ediyor ve `position: fixed` arka plan katmanı (BackgroundLayer) bu kaymayla
 * birlikte görsel olarak sürükleniyor. Bunun yerine body'nin kendisi
 * `position: fixed` yapılıyor — fixed bir eleman TOUCH ile de kaydırılamaz,
 * bu yüzden arka plan artık hareket edemez. Kapanışta önceki scroll konumu
 * `top` değerinden okunup geri yükleniyor.
 */
export function useScrollLock() {
  useEffect(() => {
    const { body, documentElement } = document;
    const scrollY = window.scrollY;
    const scrollbarWidth = window.innerWidth - documentElement.clientWidth;
    const previous = {
      position: body.style.position,
      top: body.style.top,
      left: body.style.left,
      right: body.style.right,
      width: body.style.width,
      paddingRight: body.style.paddingRight,
    };

    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";
    // Scrollbar kaybolunca sayfa genişliği artıp içerik kayacağı için
    // (Windows/Linux gibi overlay olmayan scrollbar'larda) o genişlik kadar
    // sağa padding eklenip telafi ediliyor.
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`;
    }

    return () => {
      body.style.position = previous.position;
      body.style.top = previous.top;
      body.style.left = previous.left;
      body.style.right = previous.right;
      body.style.width = previous.width;
      body.style.paddingRight = previous.paddingRight;
      window.scrollTo(0, scrollY);
    };
  }, []);
}
