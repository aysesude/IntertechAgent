import { act } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { SurveyResult, SurveyRule } from "@/api/survey";

/**
 * Anket sihirbazının SONUÇ EKRANI testleri.
 *
 * Ağırlık çelişki (durdurucu kural) durumunda: bu ekran ilk girişteki
 * KAPATILAMAZ kapının içinde çiziliyor. Kullanıcı burada tıkandığında
 * uygulamaya hiç giremiyor, dolayısıyla "neyi düzelteceğim" sorusunun
 * cevabı ekranda YAZILI olmak zorunda.
 *
 * Bir kez kırıldı: kurallar `!k.durdurucu` ile süzülüyordu, yani tam da
 * sebebi açıklayan mesaj gizleniyordu. Sunucu kuralı döndürüyordu
 * (`test_survey_submit_api.py` bunu ayrıca doğruluyor), `api/survey.ts`
 * sözleşmeyi belgeliyordu; eksik olan yalnızca gösterimdi.
 */

vi.mock("@/context/ThemeContext", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

const fetchSurveyQuestions = vi.fn();
vi.mock("@/api/survey", () => ({
  fetchSurveyQuestions: () => fetchSurveyQuestions(),
}));

const { SurveyWizard } = await import("./SurveyWizard");
const { SURVEY_STEPS } = await import("@/components/auth/registerSteps");

/** Config'in kendisi değil, ŞEKLİ taklit ediliyor: bu test skorlamayı
 *  sınamıyor (onu `tests/test_survey_scoring.py` yapıyor), sonucun nasıl
 *  gösterildiğini sınıyor. */
const QUESTIONS = {
  meta: {},
  sorular: Object.fromEntries(
    SURVEY_STEPS.flatMap((adim) => adim.sorular).map((kod) => [
      kod,
      {
        t: `${kod} sorusu`,
        o: [
          ["a", "Birinci seçenek"],
          ["b", "İkinci seçenek"],
        ],
      },
    ]),
  ),
  urun_matrisi: {
    satirlar: [
      { k: "r1", n: "Çok düşük riskli", ex: "Repo–ters repo", w: 1 },
      { k: "r4", n: "Yüksek riskli", ex: "VİOP türev işlemleri", w: 4 },
    ],
    sutunlar: [
      {
        k: "bilgi",
        l: "Bilgi",
        o: [
          ["0", "Bilgim yok"],
          ["2", "Yeterli"],
        ],
      },
      {
        k: "siklik",
        l: "Sıklık",
        o: [
          ["0", "Hiç"],
          ["3", "Sıklıkla"],
        ],
      },
      {
        k: "hacim",
        l: "Hacim",
        o: [
          ["0", "İşlem yok"],
          ["2", "500 B – 5 M"],
        ],
      },
    ],
  },
  profiller: [],
  arac_sirasi: [],
  araclar: {},
};

const TK1: SurveyRule = {
  kod: "TK1",
  durdurucu: true,
  mesaj: "Belirttiğiniz risk tercihi ile geçmiş işlem hacminiz örtüşmüyor.",
};
const TK5: SurveyRule = {
  kod: "TK5",
  durdurucu: false,
  mesaj: "Acil durum birikiminiz bulunmuyor.",
};
/** Sunucuda ölçülerek üretilen gerekçe — LLM metninden bağımsız gösterilir. */
const GEREKCE = "Risk tercihi olarak şunu seçtiniz: “Riskten olabildiğince kaçınırım”";

function sonuc(ek: Partial<SurveyResult>): SurveyResult {
  return {
    kapasite: 82,
    tolerans: 13,
    bilgi: 50,
    nihai_skor: 13,
    profil_seviyesi: null,
    profil_adi: "",
    azami_fon_risk_degeri: null,
    azami_urun_risk_kategorisi: null,
    ornek_dagilim: null,
    bilgi_nedeniyle_kisitlandi: false,
    likidite_tavani_uygulandi: false,
    sinir_bolgesinde: false,
    kurallar: [],
    sonuc_uretildi: false,
    gerekceler: [GEREKCE],
    yorum: "Cevaplarınız arasında birbiriyle çelişen noktalar var.",
    ...ek,
  };
}

beforeEach(() => {
  fetchSurveyQuestions.mockReset().mockResolvedValue(QUESTIONS);
});

/** Beş adımın tamamını ilk seçeneklerle doldurup sonucu getirir. */
async function anketiBitir(onSubmit: ReturnType<typeof vi.fn>) {
  const onDone = vi.fn();
  render(<SurveyWizard onSubmit={onSubmit} onDone={onDone} />);
  await screen.findByText("A1 sorusu");

  for (const [index, adim] of SURVEY_STEPS.entries()) {
    for (const kod of adim.sorular) {
      fireEvent.click(document.querySelector(`input[name="${kod}"][value="a"]`)!);
    }
    const sonAdim = index === SURVEY_STEPS.length - 1;
    // Son adımdaki tıklama `onSubmit`i BEKLİYOR ve sonuç geldiğinde durumu
    // güncelliyor; `act` ile sarılmazsa React o güncellemeyi test dışında
    // yapılmış sayıp uyarı basıyor. Uyarı zararsız ama gerçek bir sorunu
    // gizleyebilecek gürültü.
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: sonAdim ? "Profilimi göster" : "Devam et" }),
      );
    });
  }
  return { onDone };
}

it("celiskide hangi cevabin duzeltilecegi ekranda yazar", async () => {
  const onSubmit = vi.fn().mockResolvedValue(sonuc({ kurallar: [TK1] }));

  await anketiBitir(onSubmit);

  expect(await screen.findByText("Profil belirlenemedi")).toBeTruthy();
  // Kritik olan bu: genel "çelişki var" metni değil, KURALIN KENDİ mesajı.
  expect(screen.getByText(TK1.mesaj)).toBeTruthy();
  // Ve kullanıcının kendi cevabına atıf — sunucuda ölçülmüş gerekçe.
  expect(screen.getByText(GEREKCE)).toBeTruthy();
});

it("profil uretildiginde de gerekce gosterilir", async () => {
  // Gerekçe yalnızca reddedilene değil herkese: "profilim neden bu çıktı"
  // sorusu sonuç üretildiğinde de soruluyor.
  const onSubmit = vi.fn().mockResolvedValue(
    sonuc({
      sonuc_uretildi: true,
      profil_seviyesi: 2,
      profil_adi: "Korumacı",
      gerekceler: ["Profilinizi mali kapasiteniz belirledi"],
      yorum: "Ölçülen yatırımcı profiliniz: Korumacı.",
    }),
  );

  await anketiBitir(onSubmit);

  expect(await screen.findByText("Korumacı")).toBeTruthy();
  expect(screen.getByText("Profilinizi mali kapasiteniz belirledi")).toBeTruthy();
});

it("celiskide kullanici cevaplarina geri donebilir", async () => {
  const onSubmit = vi.fn().mockResolvedValue(sonuc({ kurallar: [TK1] }));

  const { onDone } = await anketiBitir(onSubmit);
  await screen.findByText("Profil belirlenemedi");

  // Profil üretilmediği için ilerleme düğmesi YOK; çıkış yolu düzeltmek.
  expect(screen.queryByRole("button", { name: "Devam et" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Cevapları gözden geçir" }));

  expect(await screen.findByText("A1 sorusu")).toBeTruthy();
  expect(onDone).not.toHaveBeenCalled();
});

it("profil uretildiginde uyari kurallari gosterilir ve ilerlenebilir", async () => {
  const onSubmit = vi.fn().mockResolvedValue(
    sonuc({
      sonuc_uretildi: true,
      profil_seviyesi: 2,
      profil_adi: "Korumacı",
      kurallar: [TK5],
      yorum: "Ölçülen yatırımcı profiliniz: Korumacı.",
    }),
  );

  const { onDone } = await anketiBitir(onSubmit);

  expect(await screen.findByText("Korumacı")).toBeTruthy();
  expect(screen.getByText(TK5.mesaj)).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Devam et" }));
  await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
});
