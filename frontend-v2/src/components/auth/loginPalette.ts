/**
 * Giriş ekranının kapalı renk sistemi.
 *
 * Bu ekran global `utils/colors.ts` CSS değişkenlerine BAĞLI DEĞİL: arka
 * planda bir tablo var ve renkler o esere göre elle ayarlandı. Koyu tema
 * karşılıkları `src/index.css`'teki `.dark { --color-brand / --color-navy }`
 * ile birebir aynı değerlerdir.
 *
 * Ayrı dosyada olmasının sebebi: giriş kartı ile şifre yenileme kartı aynı
 * paleti kullanıyor. İki yerde kopyalanırsa biri değiştiğinde diğeri sessizce
 * ayrışır.
 */
export const BRAND = "#2557E8";
export const NAVY = "#0B2653";

export const BRAND_DARK = "#4A7EF0";
export const NAVY_DARK = "#DCE6FA";

// Ay ışığında deniz tablosuna özgü, yalnızca koyu temada kullanılan bordo
// vurgu paleti — marka mavisi ikonlarda yaşamaya devam ediyor.
export const ACCENT_DARK = "#96384A";
export const ACCENT_DARK_LINK = "#C4697A";
export const CTA_DARK = "#6B2130";
export const CTA_DARK_HOVER = "#7E2839";
// #B04A5E, 18px ince ikon çizgilerinde sönük kalıyor — ikonlara özel bir tık
// daha parlak bordo.
export const ACCENT_DARK_ICON = "#C25668";

/** Form alanlarının ortak sınıfı: iki kartta da aynı görünsün. */
export const INPUT_CLASS =
  "h-11 w-full rounded-xl border border-[#DCE3EC] bg-white px-3.5 text-[14px] tracking-[0.04em] text-[#0B2653] outline-none transition placeholder:tracking-normal placeholder:text-[#9AA9BC] focus:border-[#2557E8] focus:ring-4 focus:ring-[#2557E8]/12 dark:border-transparent dark:bg-[rgba(240,220,200,0.05)] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#B04A5E] dark:focus:ring-[#B04A5E]/20";
