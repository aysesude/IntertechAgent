// BRAND, src/index.css'teki --color-brand CSS değişkenine referans veriyor
// (light/dark temaya göre değişir). DANGER görev gereği iki temada da sabit
// kalıyor, bilerek CSS var'a bağlanmadı.
export const BRAND = "var(--color-brand)";
export const BRAND_LIGHT = "#6C93F5";
// Işık/koyu temada aynı (marka rengiyle özdeş) — sadece koyu temada, ince
// çizgi/ilerleme çubuğu gibi küçük alanlarda BRAND'den daha parlak bir
// bordo gerektiğinde kullanılır (grafik çizgisi, risk skoru barı).
export const BRAND_BRIGHT = "var(--color-brand-bright)";
export const DANGER = "#E63946";
// Kâr/zarar göstergeleri için — light modda BRAND/DANGER ile birebir aynı,
// koyu temada brand bordoya kaydığı için ayrı, brand'den bağımsız bir
// yeşil/kırmızı çift (bkz. src/index.css .dark).
export const POSITIVE = "var(--color-positive)";
export const NEGATIVE = "var(--color-negative)";
export const INK = "var(--color-ink)";
export const INK_FAINT = "var(--color-ink-faint)";
export const INK_SOFT = "var(--color-ink-soft)";
export const LINE2 = "var(--color-line-2)";
export const SURFACE_ELEVATED = "var(--color-surface-elevated)";
// Küçük "her zaman koyu" tooltip/etiket kartçıkları (bg-ink + text-white)
// için — ink token'ı dark modda AÇIK renge döndüğünden (metin için doğru
// davranış), bu chip'lerde bilerek sabit tutuluyor (aksi halde koyu temada
// beyaz zemin + beyaz metin görünürdü).
export const FIXED_DARK_CHIP = "#0B0E14";
