import { useCallback, useLayoutEffect, useRef } from "react";

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
 * AYRICA `--app-full-vh` = `window.innerHeight` (px). Klavyeden/araç
 * çubuğundan ETKİLENMEYEN, SABİT "tam" referans yükseklik — ChatWidget'ın
 * `.chat-widget-mobile-bottom` kuralı (index.css) klavye/araç çubuğunun ne
 * kadar yer kapladığını `--app-full-vh - --app-vvh` farkından çıkarıyor.
 * BİLEREK CSS'in `100vh` BİRİMİ DEĞİL: gerçek cihazda `100vh`'nin bu
 * hesap için beklenen değere ÇÖZÜMLENMEDİĞİ (ör. güvenli alan/araç
 * çubuğu farkını nasıl ele aldığına göre) görülüp ölçülen sabit bir
 * piksel değerine geçildi — iki tarafı da JS'in ölçtüğü ham piksel
 * olunca birim çözümleme belirsizliği tamamen ortadan kalkıyor.
 *
 * `useLayoutEffect` bilerek: boyamadan ÖNCE ilk değeri yazıyor, aksi halde
 * `100vh` varsayılanından gerçek değere geçişte bir karelik zıplama olurdu.
 *
 * GERİ DÖNÜŞ DEĞERİ — dışarıdan ELLE yeniden ölçtürmek için: klavye açılış
 * ANİMASYONU sırasında iOS `visualViewport` üzerinde ARA (henüz oturmamış)
 * değerlerle `resize`/`scroll` olayları tetikleyebiliyor; bu ara değer
 * `--app-vvh`'ye yazılıp events durursa (animasyon bitince yeni bir olay
 * gelmezse) panel yanlış boyutta "donuk" kalabiliyor — kullanıcı bir şey
 * yazana kadar (o an tesadüfen başka bir olay tetiklenip düzelene kadar)
 * böyle görünüyordu. Çağıran taraf (ChatPage/ChatWidget), input `onFocus`
 * anında VE klavye animasyonu bittiği tahmini anda (bkz. o dosyalardaki
 * `sayfayiEnBasaSabitle`) bu fonksiyonu ELLE çağırıp güncel değeri tazeler.
 */
export function useVisualViewportHeight() {
  const guncelleRef = useRef<() => void>(() => {});

  useLayoutEffect(() => {
    const root = document.documentElement;
    const vv = window.visualViewport;

    const guncelle = () => {
      const yukseklik = vv ? vv.height : window.innerHeight;
      root.style.setProperty("--app-vvh", `${yukseklik}px`);
      // `window.innerHeight` klavye/araç çubuğundan etkilenmiyor — bu yüzden
      // yalnızca `resize`/`orientationchange` sırasında bile ölçmek yeterli,
      // ama burada da tazelemek zararsız (değer zaten sabit kalıyor).
      root.style.setProperty("--app-full-vh", `${window.innerHeight}px`);
    };
    guncelleRef.current = guncelle;

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
      root.style.removeProperty("--app-full-vh");
      guncelleRef.current = () => {};
    };
  }, []);

  return useCallback(() => guncelleRef.current(), []);
}
