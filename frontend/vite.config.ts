import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Test ortamı Caddy ters proxy'si arkasında çalışıyor ve host adı
    // sunucunun IP'sine bağlı (nip.io) — IP değişince host da değişir.
    // Vite bilmediği host'tan gelen isteği reddettiği için burada izin veriyoruz.
    // Yalnızca geliştirme sunucusunu etkiler; canlı ortam nginx ile servis edilir
    // (bkz. frontend/Dockerfile.prod), orada böyle bir kısıt yoktur.
    allowedHosts: [".nip.io", "localhost"],
    watch: {
      usePolling: true,
    },
  },
});
