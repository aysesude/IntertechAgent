import { apiGet, apiPost } from "./client";

/**
 * Yatırımcı risk profili anketi.
 *
 * SORULAR BURADA TANIMLI DEĞİL, sunucudan gelir. Tek doğruluk kaynağı
 * `data/risk_survey_config.json`; soru metnini TypeScript'e kopyalamak, ilk
 * içerik düzenlemesinde arayüzün eski soruyu sormaya devam etmesi ve skorun
 * SORULMAYAN bir soruya göre hesaplanması demek olurdu.
 *
 * Bu yüzden tipler kasıtlı olarak gevşek (`unknown`/indeks imzası): şeklin
 * ayrıntısını sabitlemek, config'i ikinci kez tanımlamak olur.
 */

/** Bir seçenek: `[kod, metin]` ya da `[kod, metin, puan]`. */
export type SurveyOption = [string, string] | [string, string, number];

export interface SurveyQuestion {
  /** Soru metni. */
  t: string;
  /** Neden sorulduğunun açıklaması (varsa) — kullanıcıya ipucu olarak gösterilir. */
  w?: string;
  o: SurveyOption[];
  /** `true` ise soru puan vermez, tavan uygular (B6). */
  cap?: boolean;
}

export interface SurveyMatrixRow {
  k: string;
  n: string;
  /** Örnek araçlar — kullanıcı hangi ürünü kastettiğimizi anlasın diye. */
  ex: string;
  w: number;
}

export interface SurveyMatrixColumn {
  k: string;
  l: string;
  o: SurveyOption[];
}

export interface SurveyProfile {
  lv: number;
  ad: string;
  lo: number;
  hi: number;
  cat: number;
  al: Record<string, number>;
}

export interface SurveyQuestions {
  meta: Record<string, unknown>;
  sorular: Record<string, SurveyQuestion>;
  urun_matrisi: { satirlar: SurveyMatrixRow[]; sutunlar: SurveyMatrixColumn[] };
  profiller: SurveyProfile[];
  arac_sirasi: string[];
  araclar: Record<string, unknown>;
}

export interface SurveyRule {
  kod: string;
  durdurucu: boolean;
  mesaj: string;
}

/**
 * Skorlama çıktısı.
 *
 * `sonuc_uretildi` `false` iken profil alanları `null` gelir — arayüz o
 * durumda profil GÖSTERMEZ, kullanıcıdan cevaplarını gözden geçirmesini ister.
 */
export interface SurveyResult {
  kapasite: number;
  tolerans: number;
  bilgi: number;
  nihai_skor: number;
  profil_seviyesi: number | null;
  profil_adi: string;
  azami_fon_risk_degeri: number | null;
  azami_urun_risk_kategorisi: number | null;
  ornek_dagilim: Record<string, number> | null;
  bilgi_nedeniyle_kisitlandi: boolean;
  likidite_tavani_uygulandi: boolean;
  sinir_bolgesinde: boolean;
  kurallar: SurveyRule[];
  sonuc_uretildi: boolean;
  /** Sonucu açıklayan kişiselleştirilmiş metin. Hiçbir zaman boş gelmez. */
  yorum: string;
}

/** Tek bir matris satırının cevabı. */
export interface SurveyMatrixAnswer {
  bilgi: string;
  siklik: string;
  hacim: string;
}

/** `{"B1": "c", "E1": {"r1": {...}}}` */
export type SurveyAnswers = Record<string, string | Record<string, SurveyMatrixAnswer>>;

export function fetchSurveyQuestions(): Promise<SurveyQuestions> {
  return apiGet<SurveyQuestions>("/api/survey/questions", { skipUnauthorizedHandler: true });
}

/**
 * Cevapları skorlar. HİÇBİR ŞEY KAYDETMEZ — kullanıcı henüz yok.
 * Kaydetme `/api/auth/register` ile ayrı bir adımda olur.
 */
export function scoreSurvey(answers: SurveyAnswers): Promise<SurveyResult> {
  return apiPost<SurveyResult>("/api/survey/score", { answers }, { skipUnauthorizedHandler: true });
}
