/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend taban adresi. Boşsa uygulama mock veriyle çalışır. */
  readonly VITE_API_BASE_URL?: string;
  /**
   * GEÇİCİ. Eski arayüzün (`frontend/`, port 5173) adresi. Tanımlıysa giriş
   * ekranında oraya götüren küçük bir bağlantı çıkar; tanımlı değilse bağlantı
   * HİÇ render edilmez. frontend-v2 tek arayüz olduğunda bu değişken ve onu
   * kullanan blok silinecek (bkz. LoginScreen.tsx).
   */
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
