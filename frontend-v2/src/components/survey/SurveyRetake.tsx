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
    // ORTALANMIŞ, üstten başlamıyor: `items-start` ile açıldığında kartın
    // üstünde uygulama başlığı bulanık bir şerit olarak görünüyordu.
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center overflow-y-auto bg-[#0B2653]/45 px-4 py-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Yatırımcı profilini yeniden ölç"
    >
      <div className="my-auto w-full max-w-[470px] rounded-2xl border border-line bg-white p-5 shadow-pop dark:border-transparent dark:bg-surface-elevated sm:p-6">
        {/* Başlık KÜÇÜK: hemen altında sihirbazın kendi bölüm başlığı var.
            İkisi aynı boyutta olunca ekranın üstü iki yarışan başlıkla
            kalabalıklaşıyordu. Buradaki bir kutu etiketi, sayfa başlığı
            değil. */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              className="text-[15px] font-semibold"
              style={{ color: navyColor } as CSSProperties}
            >
              Yatırımcı profilini yeniden ölç
            </h2>
            <p className="mt-0.5 text-[12px] leading-snug text-ink-soft dark:text-ink-faint">
              Yeni sonuç mevcut profilinin yerine geçer.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Kapat"
            className="-mr-1 -mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-soft transition-colors hover:bg-brand-tint hover:text-brand"
          >
            <X size={17} />
          </button>
        </div>

        <SurveyWizard
          onSubmit={gonder}
          onDone={bitir}
          bitirButonMetni="Profilimi güncelle"
          listeYuksekligi="max-h-[46vh]"
        />

        <p className="mt-3 text-center text-[11px] text-ink-soft dark:text-ink-faint">
          Bu bir yatırım tavsiyesi değildir.
        </p>
      </div>
    </div>
  );
}

export default SurveyRetake;
