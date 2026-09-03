import { useLayoutEffect } from "react";

/**
 * `--app-vvh` CSS değişkenini GERÇEK görünür yüksekliğe (px) sabitler —
 * `document.documentElement` üzerinde, `visualViewport` API'siyle.
 *
 * NEDEN `dvh` YETMİYOR: `100dvh` yalnızca tarayıcı araç çubuğunun
 * gizlenip/görünmesini hesaba katıyor — EKRAN KLAVYESİNİ DEĞİL. iOS
 * Safari'de klavye açıldığında layout viewport (ve dolayısıyla `dvh`)
 * SABİT kalır, yalnızca "visual viewport" küçülür; `dvh` ile hesaplanan
 * sabit yükseklikli bir kutu klavyenin ARKASINDA kalmaya devam eder —
 * giriş kutusu görünmez olur ya da sayfa tuhaf bir şekilde zıplar/kırpılır.
 * `visualViewport.height` ise klavye açıkken de GERÇEK görünür alanı verir;
 * Android tarayıcılarda zaten `dvh` ile tutarlıdır, ekstra zarar vermez.
 *
 * `--app-vvh`'nin `:root`'taki varsayılanı (index.css) `100vh` — bu hook
 * hiç çalışmasa (JS kapalı, çok eski tarayıcı) bile değer GEÇERLİ bir
 * uzunluk kalır, `.chat-viewport-height` kuralı hiçbir zaman geçersiz
 * (invalid) bir değere düşüp sıfırlanmaz.
 *
 * `useLayoutEffect` bilerek: boyamadan ÖNCE ilk değeri yazıyor, aksi halde
 * `100vh` varsayılanından gerçek değere geçişte bir karelik zıplama olurdu.
 */
export function useVisualViewportHeight() {
  useLayoutEffect(() => {
    const root = document.documentElement;
    const vv = window.visualViewport;

    const guncelle = () => {
      const yukseklik = vv ? vv.height : window.innerHeight;
      root.style.setProperty("--app-vvh", `${yukseklik}px`);
    };

    guncelle();

    // `resize`: klavye açılıp/kapanınca veya araç çubuğu gizlenip/görününce.
    // `scroll`: iOS'ta klavye açılırken visual viewport bir an KAYAR da —
    // yalnızca `resize` dinlemek bu ara kareyi kaçırabiliyordu.
    vv?.addEventListener("resize", guncelle);
    vv?.addEventListener("scroll", guncelle);
    // `visualViewport` desteklemeyen (çok eski) tarayıcılar için yedek.
    window.addEventListener("resize", guncelle);
    window.addEventListener("orientationchange", guncelle);

    return () => {
      vv?.removeEventListener("resize", guncelle);
      vv?.removeEventListener("scroll", guncelle);
      window.removeEventListener("resize", guncelle);
      window.removeEventListener("orientationchange", guncelle);
      root.style.removeProperty("--app-vvh");
    };
  }, []);
}
