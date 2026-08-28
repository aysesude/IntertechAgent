import { useState } from "react";
import type { CSSProperties } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { submitSurvey, type SurveyAnswers, type SurveyResult } from "@/api/survey";
import { SurveyWizard } from "@/components/survey/SurveyWizard";
import {
  ACCENT_DARK_LINK,
  BRAND,
  CTA_DARK,
  CTA_DARK_HOVER,
  NAVY,
  NAVY_DARK,
} from "@/components/auth/loginPalette";

/**
 * Anketi doldurmamış kullanıcıyı karşılayan KAPATILAMAZ adım.
 *
 * GİRİŞ KARTININ İÇİNDE AÇILIR — `PasswordResetCard` ve `RegisterCard` ile
 * aynı desen. Bir süre ayrı bir tam sayfa olarak duruyordu; arka plandaki
 * eser, kart çerçevesi ve logo orada yeniden kuruluyordu ve kullanıcı
 * "üye ol"dan sonra bambaşka bir ekrana düşmüş gibi oluyordu. Artık kayıt
 * akışının doğal devamı gibi görünüyor: aynı kart, yalnızca içeriği değişti.
 *
 * NEDEN KAPATILAMAZ: uygunluk kontrolü (`advice_eligibility`) anket puanına
 * dayanıyor. Puanı olmayan kullanıcı uygulamayı gezebilse portföyünü görür
 * ama tavsiye katmanı sessizce kapalı olurdu — eksikliği fark etmez.
 *
 * NEDEN KAYIT AKIŞININ İÇİNDE DEĞİL: burası GÖRÜNÜŞTE kaydın devamı ama
 * hesap ÇOKTAN AÇILMIŞ durumda. 18 soru kaydın içindeyken yarıda bırakan
 * kullanıcının hesabı hiç açılmıyordu; en pahalı adım en kırılgan adıma
 * bağlıydı. Şimdi anket yarıda kalsa da hesap duruyor, kullanıcı sonraki
 * girişinde kaldığı yerden devam ediyor.
 *
 * ÇIKIŞ DÜĞMESİ VAR: kullanıcı hapsedilmiyor, oturumu kapatabiliyor.
 * Kapatılamaz olan anket, uygulamanın kendisi değil.
 */

interface SurveyGateProps {
  userId: string;
  fullName: string;
}

export function SurveyGate({ userId, fullName }: SurveyGateProps) {
  const { resolvedTheme } = useTheme();
  const { logout, refreshAccount } = useAuth();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;

  const [basladi, setBasladi] = useState(false);

  const ad = fullName.trim().split(/\s+/)[0] ?? "";

  const gonder = (answers: SurveyAnswers): Promise<SurveyResult> =>
    submitSurvey(userId, answers);

  const bitir = () => {
    // Sunucu puanı yazdı; oturumdaki kullanıcı kaydını tazeleyince bu adım
    // kendiliğinden kalkar (App, `risk_survey_score` null değilse Dashboard'ı
    // çiziyor). Sayfayı yeniden yüklemek yerine tek bir istek atıyoruz.
    void refreshAccount();
  };

  const birincilButon =
    "flex h-12 w-full items-center justify-center rounded-xl text-[14.5px] font-semibold text-white transition-colors duration-200 focus:outline-none focus-visible:ring-4 focus-visible:ring-[#2557E8]/35";
  const birincilStil = {
    backgroundColor: isDark ? CTA_DARK : BRAND,
    "--cta-dark-hover": CTA_DARK_HOVER,
  } as CSSProperties;

  const cikisButon = (
    <div className="mt-3 flex justify-center">
      <button
        type="button"
        onClick={logout}
        style={{ "--accent-dark-link": ACCENT_DARK_LINK } as CSSProperties}
        className="rounded text-[12.5px] font-medium text-[#5A7292] underline-offset-4 transition hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2557E8]/40 dark:text-[var(--accent-dark-link)]"
      >
        Çıkış yap
      </button>
    </div>
  );

  if (basladi) {
    return (
      <div>
        <SurveyWizard onSubmit={gonder} onDone={bitir} bitirButonMetni="Panele geç" />
        {cikisButon}
        <p className="mt-4 text-center text-[11.5px] text-[#7A8CA4] dark:text-[#9AACC7]">
          Bu bir yatırım tavsiyesi değildir.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2
        className="mt-6 font-display text-[27px] font-semibold leading-tight tracking-[-0.015em]"
        style={{ color: navyColor }}
      >
        {ad ? `Hoş geldin, ${ad}` : "Hoş geldin"}
      </h2>
      <p className="mt-3 text-[13.5px] leading-relaxed text-[#3F5878] dark:text-[#B9C4DC]">
        Hesabın hazır. Sana uygun yorumları yapabilmemiz için önce yatırımcı
        profilini ölçmemiz gerekiyor.
      </p>

      {/* Kullanıcıya ne beklediğini SÖYLÜYORUZ. 18 soruluk bir anketi haber
          vermeden başlatmak, üçüncü ekranda bırakılmasının en yaygın sebebi. */}
      <div className="mt-5 rounded-xl border border-[#DCE3EC] bg-white/60 px-4 py-3.5 text-[13px] leading-relaxed text-[#5A7292] dark:border-transparent dark:bg-white/[0.05] dark:text-[#B9C4DC]">
        Beş bölüm, yaklaşık 5 dakika. Mali durumunu, hedeflerini ve piyasa
        deneyimini soruyoruz. Sonunda profilini ve neden o profile girdiğini
        açıklıyoruz.
      </div>

      <p className="mt-4 text-[12.5px] leading-relaxed text-[#7A8CA4] dark:text-[#9AACC7]">
        Bu adımı atlayamıyoruz. Profilini bilmeden sana uygun olup olmadığından
        emin olamadığımız bir yatırım önerme riskimiz var.
      </p>

      <button
        type="button"
        onClick={() => setBasladi(true)}
        className={`${birincilButon} mt-6`}
        style={birincilStil}
      >
        Ankete başla
      </button>

      {cikisButon}
    </div>
  );
}

export default SurveyGate;
