import type { CSSProperties } from "react";
import { X } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { submitSurvey, type SurveyAnswers, type SurveyResult } from "@/api/survey";
import { SurveyWizard } from "@/components/survey/SurveyWizard";
import { NAVY, NAVY_DARK } from "@/components/auth/loginPalette";

/**
 * Yatırımcı profilini YENİDEN ölçme katmanı — kullanıcı menüsünden açılır.
 *
 * NEDEN AYRI BİLEŞEN, `SurveyGate` DEĞİL: ikisi aynı sihirbazı çiziyor ama
 * sözleşmeleri zıt. Kapı KAPATILAMAZ (puanı olmayan kullanıcı uygulamaya
 * giremez); bu katman KAPATILABİLİR olmak zorunda, çünkü kullanıcının zaten
 * geçerli bir puanı var ve vazgeçtiğinde kaybedeceği bir şey yok. Aynı
 * bileşene "bazen kapanır bazen kapanmaz" davranışı koymak, kapının
 * kapatılamazlığını bir bayrağa indirger ve ileride yanlışlıkla açılmasına
 * açık hâle getirir.
 *
 * PROFİL DEĞİŞEBİLİR: yeni cevaplar sunucuda yeniden skorlanır ve
 * `users.risk_survey_score` ÜZERİNE YAZILIR. Puan değişince risk profili de
 * ondan türetilir; uygunluk kontrolü bir sonraki soruda yeni seviyeye göre
 * çalışır.
 *
 * ÇELİŞKİDE ESKİ PUAN KORUNUR: durdurucu bir kural tetiklenirse sunucu hiçbir
 * şey yazmaz. Yani yarıda bırakılan ya da tutarsız bir yeniden ölçüm,
 * kullanıcının mevcut profilini BOZMAZ — en kötü ihtimalle hiçbir şey değişmez.
 */

interface SurveyRetakeProps {
  userId: string;
  onClose: () => void;
}

export function SurveyRetake({ userId, onClose }: SurveyRetakeProps) {
  const { resolvedTheme } = useTheme();
  const { refreshAccount } = useAuth();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;

  const gonder = (answers: SurveyAnswers): Promise<SurveyResult> =>
    submitSurvey(userId, answers);

  const bitir = () => {
    // Sunucu puanı yazdı; oturumdaki kullanıcı kaydını tazeleyince yeni
    // seviye uygulamanın tamamına yayılır.
    void refreshAccount();
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-[#0B2653]/45 px-4 py-8 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Yatırımcı profilini yeniden ölç"
    >
      <div className="w-full max-w-[560px] rounded-[26px] border border-line bg-white p-7 shadow-pop dark:border-transparent dark:bg-surface-elevated sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              className="font-display text-[22px] font-semibold tracking-[-0.015em]"
              style={{ color: navyColor } as CSSProperties}
            >
              Yatırımcı profilini yeniden ölç
            </h2>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-soft dark:text-ink-faint">
              Mali durumun ya da hedeflerin değiştiyse anketi tekrar
              doldurabilirsin. Yeni sonuç mevcut profilinin yerine geçer.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Kapat"
            className="-mr-1 -mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-lg text-ink-soft transition-colors hover:bg-brand-tint hover:text-brand"
          >
            <X size={18} />
          </button>
        </div>

        <SurveyWizard onSubmit={gonder} onDone={bitir} bitirButonMetni="Profilimi güncelle" />

        <p className="mt-4 text-center text-[11.5px] text-ink-soft dark:text-ink-faint">
          Bu bir yatırım tavsiyesi değildir.
        </p>
      </div>
    </div>
  );
}

export default SurveyRetake;
