import { useState } from "react";
import type { CSSProperties } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { useAuth } from "@/auth/AuthContext";
import { submitSurvey, type SurveyAnswers, type SurveyResult } from "@/api/survey";
import { SurveyWizard } from "@/components/survey/SurveyWizard";
import {
  BRAND,
  CTA_DARK,
  CTA_DARK_HOVER,
  NAVY,
  NAVY_DARK,
} from "@/components/auth/loginPalette";

/**
 * Anketi doldurmamış kullanıcıyı karşılayan KAPATILAMAZ ekran.
 *
 * NEDEN KAPATILAMAZ: uygunluk kontrolü (`advice_eligibility`) anket puanına
 * dayanıyor. Puanı olmayan kullanıcı uygulamayı gezebilse, portföyünü görür
 * ama tavsiye katmanı sessizce kapalı olurdu — kullanıcı eksikliği fark
 * etmez, "sistem bana bir şey söylemiyor" diye düşünürdü. Eksik olanı
 * söylemek ve tamamlatmak, sessizce yarım çalışmaktan iyidir.
 *
 * NEDEN AYRI EKRAN, MODAL DEĞİL: 18 soru + matris bir modala sığmıyor;
 * kaydırmalı bir modal hem dar hem de "kapatılabilir" hissi veriyor.
 *
 * ÇIKIŞ DÜĞMESİ VAR: kullanıcı hapsedilmiyor, oturumu kapatabiliyor.
 * Kapatılamaz olan anket, uygulamanın kendisi değil.
 */

interface SurveyGateProps {
  userId: string;
  fullName: string;
}

export function SurveyGate({ userId, fullName }: SurveyGateProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const { logout, refreshAccount } = useAuth();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;

  const [basladi, setBasladi] = useState(false);

  const ad = fullName.trim().split(/\s+/)[0] ?? "";

  const gonder = (answers: SurveyAnswers): Promise<SurveyResult> =>
    submitSurvey(userId, answers);

  const bitir = () => {
    // Sunucu puanı yazdı; oturumdaki kullanıcı kaydını tazeleyince bu ekran
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

  return (
    <div className="relative min-h-[100dvh] w-full overflow-y-auto bg-[#EAF0F7] dark:bg-[#0A0F16]">
      <button
        type="button"
        onClick={() => setTheme(isDark ? "light" : "dark")}
        aria-label={isDark ? "Açık temaya geç" : "Koyu temaya geç"}
        className="absolute right-5 top-5 z-10 flex h-10 w-10 items-center justify-center rounded-full border border-white/70 bg-white/80 text-[#0B2653] shadow-[0_6px_20px_-12px_rgba(11,38,83,0.5)] transition-colors hover:bg-white dark:border-transparent dark:bg-white/10 dark:text-[#DCE6FA] dark:hover:bg-white/20"
      >
        {isDark ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <div className="mx-auto flex min-h-[100dvh] w-full max-w-[620px] flex-col justify-center px-5 py-12">
        <img
          src="/vira_logo_text.svg"
          alt="Vira"
          className="mb-8 h-10 w-auto self-start dark:[filter:brightness(0)_invert(1)]"
          draggable={false}
        />

        <div className="rounded-[26px] border border-line bg-white/70 p-7 shadow-[0_28px_70px_-30px_rgba(11,38,83,0.35)] backdrop-blur-xl dark:border-transparent dark:bg-white/[0.04] sm:p-8">
          {basladi ? (
            <SurveyWizard onSubmit={gonder} onDone={bitir} bitirButonMetni="Panele geç" />
          ) : (
            <>
              <h1
                className="font-display text-[27px] font-semibold leading-tight tracking-[-0.015em]"
                style={{ color: navyColor }}
              >
                {ad ? `Hoş geldin, ${ad}` : "Hoş geldin"}
              </h1>
              <p className="mt-3 text-[14px] leading-relaxed text-[#3F5878] dark:text-[#B9C4DC]">
                Hesabın hazır. Sana uygun yorumları yapabilmemiz için önce
                yatırımcı profilini ölçmemiz gerekiyor.
              </p>

              {/* Kullanıcıya ne beklediğini SÖYLÜYORUZ. 18 soruluk bir anketi
                  haber vermeden başlatmak, üçüncü ekranda bırakılmasının en
                  yaygın sebebi. */}
              <div className="mt-5 rounded-xl border border-line bg-white/60 px-4 py-3.5 text-[13px] leading-relaxed text-[#5A7292] dark:border-transparent dark:bg-white/[0.05] dark:text-[#B9C4DC]">
                Beş bölüm, yaklaşık 5 dakika. Mali durumunu, hedeflerini ve
                piyasa deneyimini soruyoruz. Sonunda profilini ve neden o
                profile girdiğini açıklıyoruz.
              </div>

              <p className="mt-4 text-[12.5px] leading-relaxed text-[#7A8CA4] dark:text-[#9AACC7]">
                Bu adımı atlayamıyoruz. Profilini bilmeden sana uygun olup
                olmadığından emin olamadığımız bir yatırım önerme riskimiz var.
              </p>

              <button
                type="button"
                onClick={() => setBasladi(true)}
                className={`${birincilButon} mt-6`}
                style={birincilStil}
              >
                Ankete başla
              </button>

              <div className="mt-3 flex justify-center">
                <button
                  type="button"
                  onClick={logout}
                  className="rounded text-[12.5px] font-medium text-[#5A7292] underline-offset-4 transition hover:underline dark:text-[#9AACC7]"
                >
                  Çıkış yap
                </button>
              </div>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-[11.5px] text-[#7A8CA4] dark:text-[#9AACC7]">
          Bu bir yatırım tavsiyesi değildir.
        </p>
      </div>
    </div>
  );
}

export default SurveyGate;
