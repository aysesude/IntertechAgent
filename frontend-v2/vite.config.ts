import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5174,
    host: true,
    // Test ortamı Caddy ters proxy'si arkasında çalışıyor ve host adı
    // sunucunun IP'sine bağlı (nip.io) — IP değişince host da değişir.
    // Vite 5.4.12'den beri bilmediği host'tan gelen isteği reddediyor
    // (DNS rebinding koruması), o yüzden burada izin veriyoruz. Baştaki
    // nokta alt alan adlarını da kapsar: v2.test.<ip>.nip.io dahil.
    // Yalnızca geliştirme sunucusunu etkiler; canlı ortam nginx ile servis
    // edilir (bkz. Dockerfile.prod), orada böyle bir kısıt yoktur.
    // frontend/vite.config.ts ile bilerek aynı — iki arayüz aynı ters
    // proxy'nin arkasında duruyor, ayrışmaları için sebep yok.
    allowedHosts: [".nip.io", "localhost"],
    watch: {
      // Kaynak kodu konteynere bind mount ediliyor; bazı dosya sistemlerinde
      // inotify olayları konteynere ulaşmıyor ve sıcak yenileme sessizce
      // çalışmıyor. frontend/ ile aynı gerekçe.
      usePolling: true,
    },
  },
});
