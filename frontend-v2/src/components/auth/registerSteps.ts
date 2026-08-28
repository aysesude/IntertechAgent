/**
 * Kayıt sihirbazının adım tanımı.
 *
 * SORU SIRASI SABİT ve bu kasıtlı: entegrasyon kılavuzunun açık uyarısı —
 * sıra değişikliği çıpalama etkisiyle skoru kaydırır ve geçmiş sonuçlarla
 * karşılaştırılabilirliği bozar. Bu dizi config'teki sırayı korur.
 *
 * Adım metinleri BURADA, soru metinleri DEĞİL: sorular sunucudan gelir
 * (`/api/survey/questions`). Buradakiler yalnızca bölüm başlıklarıdır —
 * config'te bölüm adı alanı yok ve kullanıcıya "A bölümü" demek anlamsız.
 */

export interface SurveyStep {
  /** Bölüm başlığı. */
  baslik: string;
  /** Kullanıcıya bu bölümde ne sorulduğunu anlatan bir cümle. */
  aciklama: string;
  /** Bu adımda sorulacak soru kodları, config sırasıyla. */
  sorular: string[];
  /** `true` ise E1 ürün matrisi de bu adımda çizilir. */
  matris?: boolean;
}

export const SURVEY_STEPS: SurveyStep[] = [
  {
    baslik: "Sizi tanıyalım",
    aciklama: "Yatırım ufkunuzu doğru ölçmek için birkaç temel bilgi.",
    sorular: ["A1", "A2", "A4"],
  },
  {
    baslik: "Mali durumunuz",
    aciklama: "Risk KAPASİTENİZİ belirler: ne kadar riski taşıyabilirsiniz.",
    sorular: ["B1", "B2", "B3", "B4", "B5", "B6"],
  },
  {
    baslik: "Hedefleriniz",
    aciklama: "Parayı ne için ve ne kadar süreyle ayırdığınız.",
    sorular: ["C1", "C2", "C3"],
  },
  {
    baslik: "Piyasa karşısında tutumunuz",
    aciklama: "Risk TOLERANSINIZI belirler: ne kadar riski taşımak istersiniz.",
    sorular: ["D1", "D2", "D3"],
  },
  {
    baslik: "Bilgi ve deneyiminiz",
    aciklama: "Hangi ürünleri tanıdığınız ve ne sıklıkta işlem yaptığınız.",
    sorular: ["E2", "E3", "E4"],
    matris: true,
  },
];

/**
 * Kayıt sihirbazının aşamaları. Anket ARTIK BURADA DEĞİL — ilk girişe
 * taşındı (components/survey/SurveyGate.tsx), kayıt iki adıma indi.
 */
export type WizardStage = "hesap" | "aktarim";
