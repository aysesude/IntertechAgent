import { useMemo, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { useTheme } from "@/context/ThemeContext";
import {
  ACCENT_DARK,
  ACCENT_DARK_LINK,
  BRAND,
  CTA_DARK,
  CTA_DARK_HOVER,
  INPUT_CLASS,
  NAVY,
  NAVY_DARK,
} from "@/components/auth/loginPalette";
import type { WizardStage } from "@/components/auth/registerSteps";
import { useAuth } from "@/auth/AuthContext";
import { gecerliTcKimlikNo } from "@/utils/tckn";
import { formatTRY } from "@/utils/format";

/**
 * Hesap açma sihirbazı — giriş kartının İÇİNDE açılır.
 *
 * `PasswordResetCard` ile aynı desen: ayrı bir sayfaya gitmek arka plandaki
 * eseri, kart çerçevesini ve logoyu yeniden kurmak demek olurdu. Yalnızca
 * kartın içeriği değişiyor.
 *
 * AKIŞ İKİ ADIM: hesap bilgileri → açılış aktarımı.
 *
 * ANKET BURADA DEĞİL, İLK GİRİŞTE (`components/survey/SurveyGate.tsx`).
 * 18 soru + ürün matrisi kayıt akışının içindeyken, kullanıcı yarıda
 * bıraktığında hesap HİÇ açılmıyordu — en pahalı adım (hesap açma) en
 * kırılgan adıma (uzun form) bağlıydı. Artık hesap açılıyor, anket puanı
 * boş kalıyor ve kullanıcı girişte kapatılamaz bir ekranla karşılaşıyor;
 * yarım kalan anket hesabı kaybettirmiyor.
 */

interface RegisterCardProps {
  onBack: () => void;
}

export function RegisterCard({ onBack }: RegisterCardProps) {
  const { register } = useAuth();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;
  const accent = isDark ? ACCENT_DARK : BRAND;

  const [stage, setStage] = useState<WizardStage>("hesap");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Hesap bilgileri
  const [fullName, setFullName] = useState("");
  const [tckn, setTckn] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Aktarım
  const [tutar, setTutar] = useState("");

  const toplamAdim = 2;
  const mevcutAdim = stage === "hesap" ? 1 : 2;

  const tutarSayi = useMemo(() => {
    const temiz = tutar.replace(/\./g, "").replace(",", ".");
    const n = Number(temiz);
    return Number.isFinite(n) ? n : 0;
  }, [tutar]);

  /* ---------------------------------------------------------------- */
  /*  Adım geçişleri                                                   */
  /* ---------------------------------------------------------------- */

  const hesapDevam = (e: FormEvent) => {
    e.preventDefault();
    // İstemci doğrulaması yalnızca kullanıcı konforu içindir; asıl kapı
    // sunucudadır (backend/app/schemas/auth.py).
    if (fullName.trim().split(/\s+/).filter(Boolean).length < 2) {
      setError("Ad ve soyadınızı birlikte yazın.");
      return;
    }
    if (!gecerliTcKimlikNo(tckn)) {
      setError("T.C. kimlik numarası 11 haneli olmalı.");
      return;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError("Geçerli bir e-posta adresi yazın.");
      return;
    }
    if (password.length !== 6) {
      setError("Şifre 6 haneli olmalı.");
      return;
    }
    setError(null);
    setStage("aktarim");
  };

  const kaydet = async () => {
    setError(null);
    setBusy(true);
    try {
      await register({
        full_name: fullName.trim(),
        national_id: tckn,
        email: email.trim(),
        password,
        // Metin olarak gidiyor: sunucu tarafı `Decimal`, kayan noktaya
        // çevirmek büyük tutarlarda kuruş kaybettirir.
        initial_deposit_try: tutarSayi.toFixed(2),
      });
      // Başarılıysa AuthProvider oturumu açar. Anket puanı boş olduğu için
      // App, Dashboard yerine anket ekranını çizecek.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hesap açılamadı.");
      setBusy(false);
    }
  };

  /* ---------------------------------------------------------------- */
  /*  Ortak parçalar                                                   */
  /* ---------------------------------------------------------------- */

  const birincilButon =
    "flex h-12 w-full items-center justify-center gap-2 rounded-xl text-[14.5px] font-semibold text-white transition-colors duration-200 focus:outline-none focus-visible:ring-4 focus-visible:ring-[#2557E8]/35 disabled:cursor-not-allowed disabled:opacity-70";
  const birincilStil = {
    backgroundColor: isDark ? CTA_DARK : BRAND,
    "--cta-dark-hover": CTA_DARK_HOVER,
  } as CSSProperties;

  const geriButon =
    "rounded text-[12.5px] font-medium text-[#5A7292] underline-offset-4 transition hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2557E8]/40 dark:text-[var(--accent-dark-link)]";
  const geriStil = { "--accent-dark-link": ACCENT_DARK_LINK } as CSSProperties;

  const hataSatiri = error && (
    <p role="alert" className="mt-4 text-[12.5px] text-[#E63946] dark:text-[#FF8A90]">
      {error}
    </p>
  );

  return (
    <div>
      {/* İlerleme: iki adım kısa ama kullanıcı kaç adım kaldığını görsün;
          ne kadar kaldığını görmezse yarıda bırakır. */}
      <div className="mt-6 flex items-center gap-2">
        {Array.from({ length: toplamAdim }, (_, i) => (
          <span
            key={i}
            className="h-1 flex-1 rounded-full transition-colors"
            style={{
              backgroundColor:
                i < mevcutAdim ? accent : isDark ? "rgba(255,255,255,0.14)" : "#DCE3EC",
            }}
          />
        ))}
      </div>
      <p className="mt-2 text-[11.5px] font-medium text-[#7A8CA4] dark:text-[#9AACC7]">
        Adım {mevcutAdim} / {toplamAdim}
      </p>

      {/* ---------------------------------------------------------- */}
      {stage === "hesap" && (
        <>
          <h2
            className="mt-4 font-display text-[27px] font-semibold tracking-[-0.015em]"
            style={{ color: navyColor }}
          >
            Aramıza hoş geldin
          </h2>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            Önce hesabını açalım, sonra yatırımcı profilini birlikte ölçelim.
          </p>

          <form onSubmit={hesapDevam} className="mt-6 space-y-4" noValidate>
            <div>
              <label
                htmlFor="reg-name"
                className="mb-1.5 block text-[12.5px] font-medium"
                style={{ color: navyColor }}
              >
                Ad Soyad
              </label>
              <input
                id="reg-name"
                autoComplete="name"
                autoFocus
                placeholder="Adın ve soyadın"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className={INPUT_CLASS}
              />
            </div>

            <div>
              <label
                htmlFor="reg-tckn"
                className="mb-1.5 block text-[12.5px] font-medium"
                style={{ color: navyColor }}
              >
                T.C. Kimlik Numarası
              </label>
              <input
                id="reg-tckn"
                inputMode="numeric"
                maxLength={11}
                placeholder="11 haneli kimlik numaran"
                value={tckn}
                onChange={(e) => setTckn(e.target.value.replace(/\D/g, "").slice(0, 11))}
                className={INPUT_CLASS}
              />
            </div>

            <div>
              <label
                htmlFor="reg-email"
                className="mb-1.5 block text-[12.5px] font-medium"
                style={{ color: navyColor }}
              >
                E-posta
              </label>
              <input
                id="reg-email"
                type="email"
                autoComplete="email"
                placeholder="ornek@eposta.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={INPUT_CLASS}
              />
            </div>

            <div>
              <label
                htmlFor="reg-password"
                className="mb-1.5 block text-[12.5px] font-medium"
                style={{ color: navyColor }}
              >
                Şifre
              </label>
              <input
                id="reg-password"
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={6}
                placeholder="6 haneli şifre belirle"
                value={password}
                onChange={(e) => setPassword(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className={INPUT_CLASS}
              />
            </div>

            {hataSatiri}

            <button type="submit" className={birincilButon} style={birincilStil}>
              Devam et
            </button>

            <div className="flex justify-center">
              <button type="button" onClick={onBack} className={geriButon} style={geriStil}>
                Zaten hesabım var, giriş yap
              </button>
            </div>
          </form>
        </>
      )}

      {/* ---------------------------------------------------------- */}
      {stage === "aktarim" && (
        <>
          <h2
            className="mt-4 font-display text-[24px] font-semibold tracking-[-0.015em]"
            style={{ color: navyColor }}
          >
            Hesabına para aktar
          </h2>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            Başka bir bankadaki hesabından VİRA hesabına aktarmak istediğin
            tutarı yaz. İstersen bu adımı boş bırakıp sonra da aktarabilirsin.
          </p>

          <div className="mt-6">
            <label
              htmlFor="reg-tutar"
              className="mb-1.5 block text-[12.5px] font-medium"
              style={{ color: navyColor }}
            >
              Tutar (TL)
            </label>
            <input
              id="reg-tutar"
              inputMode="decimal"
              autoFocus
              placeholder="Örneğin 50000"
              value={tutar}
              onChange={(e) => setTutar(e.target.value.replace(/[^\d.,]/g, ""))}
              className={INPUT_CLASS}
            />
            {tutarSayi > 0 && (
              <p className="mt-2 text-[12.5px] text-[#5A7292] dark:text-[#B9C4DC]">
                Hesabına {formatTRY(tutarSayi)} aktarılacak.
              </p>
            )}
          </div>

          {hataSatiri}

          <button
            type="button"
            onClick={kaydet}
            disabled={busy}
            className={`${birincilButon} mt-5`}
            style={birincilStil}
          >
            {busy ? "Hesabın açılıyor…" : "Hesabımı aç"}
          </button>

          <div className="mt-3 flex justify-center">
            <button
              type="button"
              onClick={() => {
                setError(null);
                setStage("hesap");
              }}
              className={geriButon}
              style={geriStil}
            >
              Geri
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default RegisterCard;
