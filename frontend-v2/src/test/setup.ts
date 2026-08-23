import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/**
 * React'e "buradası bir test ortamı" demek zorundayız; aksi halde doğrudan
 * `act()` çağıran testlerde React "not configured to support act(...)" uyarısı
 * basıyor ve durum güncellemelerinin ne zaman akıtıldığı garanti olmuyor —
 * yani test geçse bile güvenilir olmuyor.
 */
declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

/**
 * Her testten sonra render edilen ağacı söker.
 *
 * Testing Library bunu `globals: true` iken kendisi yapıyor; biz globals'ı
 * kapalı tuttuğumuz için (bkz. vitest.config.ts) elle kaydediyoruz. Olmazsa
 * bir testte mount edilen bileşen sonraki testte de DOM'da kalır ve
 * `getByText` gibi sorgular "birden fazla eşleşme" hatası verir.
 */
afterEach(() => {
  cleanup();
});
