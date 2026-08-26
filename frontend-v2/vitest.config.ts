import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

/**
 * Test yapılandırması uygulama yapılandırmasından AYRI dosyada: `vite.config.ts`
 * canlı derlemeyi tarif ediyor, testin oraya sızmasına gerek yok. Yol takma
 * adları (`@/...`) gibi ortak ayarlar `mergeConfig` ile devralınıyor, iki yerde
 * tekrarlanmıyor.
 *
 * `globals` KAPALI: her test dosyası `describe/it/expect`i vitest'ten açıkça
 * import ediyor (mevcut `src/utils/insights.test.ts` da öyle yazılmış).
 * Böylece tsconfig'e `types: ["vitest/globals"]` eklemek gerekmiyor — o alan
 * yazıldığı anda otomatik dahil edilen tüm @types paketlerini kapatıyor ve
 * ayrı bir bakım yükü doğuruyor.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      // AuthContext gibi bileşenler `window.localStorage` ve DOM istiyor.
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      // Bileşenler Tailwind sınıflarıyla çalışıyor ama testler görünüme değil
      // davranışa bakıyor; CSS'i işlemek yalnızca süre eklerdi.
      css: false,
    },
  }),
);
