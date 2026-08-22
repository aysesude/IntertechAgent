import { useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

/**
 * LoginScreen — "Finansal rotanı birlikte çizelim."
 *
 * Arka plan sanat eseri: light modda Halit, "Boğaziçi Yalıları", 1920
 * (yağlıboya) — görsel hiçbir şekilde manipüle edilmiyor, sadece
 * okunabilirlik için üstüne çok hafif beyaz gradient katmanları biniyor.
 * Dark modda ayrı bir tablo (ay ışığında deniz) kullanılıyor, kendi
 * overlay'iyle — bkz. resolvedTheme'e göre seçilen backgroundArt.
 *
 * Asset:  src/assets/login/bogazici-yalilari.jpg (light)
 *         src/assets/login/ay-isigi-deniz.jpg (dark)
 * Logo:   public/vira_logo_text.svg  (mevcut marka dosyası, değiştirilmedi)
 */
import bosphorusArt from "../assets/login/bogazici-yalilari.jpg";
import moonlitSeaArt from "../assets/login/ay-isigi-deniz.jpg";

/* ------------------------------------------------------------------ */
/*  Sabitler                                                           */
/* ------------------------------------------------------------------ */

const BRAND = "#2557E8";
const NAVY = "#0B2653";
// LoginScreen kendi kapalı renk sistemini kullanıyor (global utils/colors.ts
// CSS var'larına bağlı değil) — dark modda bu ikisinin karşılığı, ThemeContext
// üzerinden okunan resolvedTheme'e göre elle seçiliyor. Değerler src/index.css
// .dark { --color-brand / --color-navy } ile birebir aynı.
// FeatureCards ikonları artık ACCENT_DARK_ICON kullanıyor — BRAND_DARK bu
// dosyada şu an başka bir yerde tüketilmiyor, ama silinmemesi istendiği için
// export edildi (tsc'nin noUnusedLocals'ı aksi halde build'i kırar).
export const BRAND_DARK = "#4A7EF0";
const NAVY_DARK = "#DCE6FA";
// Ay ışığında deniz tablosuna özgü, dark-mode-only bordo vurgu paleti —
// marka mavisi ikonlarda yaşamaya devam ediyor, bordo sadece başlık/link/CTA'da.
const ACCENT_DARK = "#96384A"; // başlık vurgusu
const ACCENT_DARK_LINK = "#C4697A"; // bağlantı
const CTA_DARK = "#6B2130"; // buton dolgusu
const CTA_DARK_HOVER = "#7E2839"; // buton hover
// #B04A5E, FeatureCards'taki 18px ince ikon çizgilerinde sönük kalıyor —
// ikonlara özel bir tık daha parlak bir bordo.
const ACCENT_DARK_ICON = "#C25668";

/**
 * object-position değerleri (0 = sol/üst, 0.5 = orta, 1 = sağ/alt).
 */
const OBJECT_POS_X = 0.5;
const OBJECT_POS_Y = 0.5;

/**
 * App.tsx (LoginScreen→Dashboard crossfade) ve PageTransition.tsx
 * (dashboard kart stagger'ı) tarafından kullanılıyor — tek kaynak burada.
 */
export const INTRO_TIMING = {
  /**
   * Faz 4 → 5 el değişimi: LoginScreen, App.tsx'te LoginExitOverlay ile bu
   * sürede fade-out olurken Dashboard aynı sürede fade-in olur (crossfade,
   * bkz. PageTransition.tsx).
   */
  loginHandoffMs: 200,
  /** Faz 5 (Dashboard tarafı): finans kartları arası stagger. */
  dashboardCardStaggerMs: 90,
} as const;

const Z_LAYER = {
  background: 0,
  content: 20,
  toggle: 50,
} as const;

/* ------------------------------------------------------------------ */
/*  İkonlar (ince çizgisel, bağımlılıksız)                             */
/* ------------------------------------------------------------------ */

type IconProps = { className?: string };
const iconBase = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const AnalysisIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <path d="M3 20h18" />
    <path d="M6 16V9" />
    <path d="M11 16V5" />
    <path d="M16 16v-4" />
    <path d="M21 16V7" />
  </svg>
);

const RiskIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <path d="M12 3 4 6.5v5c0 4.6 3.2 8.3 8 9.5 4.8-1.2 8-4.9 8-9.5v-5L12 3Z" />
    <path d="M12 9v3.5" />
    <path d="M12 16h.01" />
  </svg>
);

const DataIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <path d="M4 17.5 9.5 12l3.5 3.5L20 8" />
    <path d="M15 8h5v5" />
  </svg>
);

const ShieldIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <rect x="4" y="10" width="16" height="10" rx="2.5" />
    <path d="M8 10V7.5a4 4 0 0 1 8 0V10" />
  </svg>
);

const EyeIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="2.75" />
  </svg>
);

const EyeOffIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <path d="M4 4l16 16" />
    <path d="M9.9 5.8A9.8 9.8 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.3 4" />
    <path d="M6.3 7.9A17.2 17.2 0 0 0 2.5 12S6 18.5 12 18.5a9.4 9.4 0 0 0 3.6-.7" />
    <path d="M9.8 10a3 3 0 0 0 4.2 4.2" />
  </svg>
);

const ArrowIcon = ({ className }: IconProps) => (
  <svg {...iconBase} className={className}>
    <path d="M4 12h15" />
    <path d="m13.5 6.5 6 5.5-6 5.5" />
  </svg>
);

/* ------------------------------------------------------------------ */
/*  Özellik kartları                                                   */
/* ------------------------------------------------------------------ */

const FEATURES = [
  {
    icon: AnalysisIcon,
    title: "Akıllı Analiz",
    body: "Portföyünü akıllıca analiz et.",
  },
  {
    icon: RiskIcon,
    title: "Risk Yönetimi",
    body: "Risklerini ölç, kontrol altında tut.",
  },
  {
    icon: DataIcon,
    title: "Veriye Dayalı Karar",
    body: "Gerçek verilerle karar al.",
  },
  {
    icon: ShieldIcon,
    title: "Güvenli Altyapı",
    body: "Bankacılık standartlarında güvenlik.",
  },
] as const;

function FeatureCards() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const iconColor = isDark ? ACCENT_DARK_ICON : BRAND;
  const titleColor = isDark ? NAVY_DARK : NAVY;

  return (
    <div className="grid max-w-[560px] grid-cols-[1fr_1fr] auto-rows-fr items-stretch gap-3">
      {FEATURES.map(({ icon: Icon, title, body }) => (
        <div
          key={title}
          className="flex h-full flex-col justify-start rounded-2xl border border-white/60 bg-white/[0.78] px-4 py-3.5 shadow-[0_8px_28px_-16px_rgba(11,38,83,0.45)] backdrop-blur-md dark:border-transparent dark:bg-[#1A1512]/[0.90] dark:shadow-[0_8px_28px_-18px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.03)]"
        >
          <div className="flex items-start gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/85 dark:bg-white/10"
              style={{ color: iconColor }}
            >
              <Icon className="h-[18px] w-[18px]" />
            </span>
            <div className="min-w-0">
              <p
                className="font-display text-[13.5px] font-semibold leading-tight"
                style={{ color: titleColor }}
              >
                {title}
              </p>
              <p className="mt-1 text-[12px] font-medium leading-snug text-[#1E3352] dark:text-[#B9C4DC]">
                {body}
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Login ekranı                                                       */
/* ------------------------------------------------------------------ */

export type LoginScreenProps = {
  /** Giriş başarılıysa çağrılır. */
  onSubmit?: (credentials: { tckn: string; password: string }) => void;
  onForgotPassword?: () => void;
};

export function LoginScreen({
  onSubmit,
  onForgotPassword,
}: LoginScreenProps) {
  const [submitted, setSubmitted] = useState(false);
  const [tckn, setTckn] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (submitted) return;
    if (tckn.length !== 11) {
      setError("T.C. kimlik numarası 11 haneli olmalı.");
      return;
    }
    if (password.length !== 6) {
      setError("Şifre 6 haneli olmalı.");
      return;
    }
    setError(null);
    setSubmitted(true);
    onSubmit?.({ tckn, password });
  };

  return (
    <div className="relative min-h-[100dvh] w-full overflow-hidden bg-[#EAF0F7] dark:bg-[#0A0F16]">
      {/* --- Tablo: light modda değiştirilmedi, sadece cover. Dark modda ayrı
          bir eser (ay ışığında deniz) — dashboard'daki gibi silik bir doku
          değil, yüksek görünürlükte (opaklık ~1) ana görsel. --- */}
      <img
        src={isDark ? moonlitSeaArt : bosphorusArt}
        alt={isDark ? "Ay ışığında deniz manzarası" : "Halit, Boğaziçi Yalıları, 1920"}
        className="absolute inset-0 h-full w-full object-cover"
        style={{
          objectPosition: `${OBJECT_POS_X * 100}% ${OBJECT_POS_Y * 100}%`,
          zIndex: Z_LAYER.background,
        }}
        draggable={false}
      />

      {/* --- Okunabilirlik katmanları (çok hafif) — SADECE light mod, hiç
          değiştirilmedi. Dark modda bunların yerine aşağıdaki vignette var. --- */}
      {!isDark && (
        <>
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.62) 0%, rgba(255,255,255,0.18) 26%, rgba(255,255,255,0) 46%)",
              zIndex: Z_LAYER.background,
            }}
          />
          <div
            className="pointer-events-none absolute inset-0 hidden lg:block"
            style={{
              background:
                "linear-gradient(90deg, rgba(255,255,255,0.34) 0%, rgba(255,255,255,0.06) 34%, rgba(255,255,255,0) 52%, rgba(255,255,255,0.30) 100%)",
              zIndex: Z_LAYER.background,
            }}
          />
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-[38%] lg:h-[30%]"
            style={{
              background:
                "linear-gradient(0deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0) 100%)",
              zIndex: Z_LAYER.background,
            }}
          />
        </>
      )}

      {/* --- Dark mod: köşelerden merkeze doğru açılan bir vignette — sol ve
          sağ kenarlar (başlık bloğunun ve login kartının arkası) koyulaşır,
          ortadaki dar dikey şerit (ay + suya düşen yansıma) elips şeklinde
          şeffaf bırakılır, tablonun can alıcı noktası kapanmaz. --- */}
      {isDark && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 40% 95% at 48% 50%, rgba(6,10,16,0) 0%, rgba(6,10,16,0) 45%, rgba(6,10,16,0.55) 75%, rgba(6,10,16,0.88) 100%)",
            zIndex: Z_LAYER.background,
          }}
        />
      )}

      {/* --- Dark mod: SADECE sol taraf (başlık bloğunun arkası) için ek
          karartma — ACCENT_DARK (#96384A) yukarıdaki radial vignette'in
          bu bölgedeki ara-ton opaklığı üzerinde tek başına 3:1'in altında
          kalıyordu. Üstteki vignette'e DOKUNULMADI (sağ/orta hâlâ aynı);
          bu ayrı katman ~%12 ek opaklıkla sadece x≈0-28 arasını
          karartıp x≈42'de sıfıra iniyor — ay/yansıma (merkez ~48%) ve
          login kartı (sağda, çok daha ileride) etkilenmiyor. --- */}
      {isDark && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, rgba(6,10,16,0.12) 0%, rgba(6,10,16,0.12) 28%, rgba(6,10,16,0) 42%)",
            zIndex: Z_LAYER.background,
          }}
        />
      )}

      {/* --- Tema toggle: Header login ekranında görünmüyor, bu yüzden
          burada küçük, sabit boyutlu bir düğme var — mevcut hiçbir öğeyle
          çakışmayan sağ üst köşede. --- */}
      <button
        type="button"
        onClick={() => setTheme(isDark ? "light" : "dark")}
        aria-label={isDark ? "Açık temaya geç" : "Koyu temaya geç"}
        className="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full border border-white/70 bg-white/80 text-[#0B2653] shadow-[0_6px_20px_-12px_rgba(11,38,83,0.5)] backdrop-blur-sm transition-colors hover:bg-white lg:right-8 lg:top-7 dark:border-white/15 dark:bg-white/10 dark:text-[#DCE6FA] dark:hover:bg-white/20"
        style={{ zIndex: Z_LAYER.toggle }}
      >
        {isDark ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      {/* --- İçerik ızgarası: %60 hikâye / %40 giriş --- */}
      <div
        className="relative mx-auto flex min-h-[100dvh] w-full max-w-[1760px] flex-col px-5 py-20 lg:grid lg:grid-cols-[60fr_40fr] lg:gap-8 lg:px-16 lg:py-0"
        style={{ zIndex: Z_LAYER.content }}
      >
        {/* Sol: hikâye */}
        <div className="flex flex-col justify-between gap-10 lg:py-16 xl:py-20">
          <div className="max-w-[620px] pt-2 lg:pt-14 lg:pl-2.5">
            <h1
              className="font-display text-[34px] font-bold leading-[1.08] tracking-[-0.025em] sm:text-[44px] lg:text-[52px] xl:text-[60px]"
              style={{ color: navyColor }}
            >
              Finansal rotanı
              <br />
              <span style={{ color: isDark ? ACCENT_DARK : BRAND }}>birlikte çizelim.</span>
            </h1>
            <p className="mt-5 max-w-[470px] text-[15px] leading-relaxed text-[#3F5878] dark:text-[#B9C4DC] lg:text-[16.5px]">
              Portföyünü analiz et, risklerini gör ve veriye dayalı kararlarını
              güvenle al.
            </p>
          </div>

          <div className="hidden lg:block">
            <FeatureCards />
            <p className="mt-5 text-[11px] font-medium tracking-wide text-[#4A6488]/70 dark:text-[#9AACC7]">
              {isDark ? "Ay Işığında Deniz" : "Halit · Boğaziçi Yalıları · 1920"}
            </p>
          </div>
        </div>

        {/* Sağ: login kartı */}
        <div className="flex items-center justify-center lg:justify-end lg:py-10 lg:pr-6">
          <div
            data-login-card
            className="w-full max-w-[452px] rounded-[26px] border border-white/70 bg-white/[0.72] p-7 backdrop-blur-2xl shadow-[0_28px_70px_-30px_rgba(11,38,83,0.45),0_2px_10px_-4px_rgba(11,38,83,0.12)] dark:border-transparent dark:bg-[#1A1512]/[0.90] dark:shadow-[0_28px_70px_-24px_rgba(0,0,0,0.65),0_0_0_1px_rgba(255,255,255,0.04)] sm:p-8"
          >
            <img
              src="/vira_logo_text.svg"
              alt="Vira"
              className="h-11 w-auto dark:[filter:brightness(0)_invert(1)]"
              draggable={false}
            />

            <h2
              className="mt-6 font-display text-[29px] font-semibold tracking-[-0.015em]"
              style={{ color: navyColor }}
            >
              Tekrar hoş geldin
            </h2>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
              Hesabına giriş yaparak finansal rotana devam et.
            </p>

            <form onSubmit={handleSubmit} className="mt-7 space-y-4" noValidate>
              <div>
                <label
                  htmlFor="tckn"
                  className="mb-1.5 block text-[12.5px] font-medium"
                  style={{ color: navyColor }}
                >
                  T.C. Kimlik Numaranız
                </label>
                <input
                  id="tckn"
                  name="tckn"
                  inputMode="numeric"
                  autoComplete="username"
                  maxLength={11}
                  placeholder="11 haneli kimlik numaran"
                  value={tckn}
                  onChange={(e) =>
                    setTckn(e.target.value.replace(/\D/g, "").slice(0, 11))
                  }
                  className="h-11 w-full rounded-xl border border-[#DCE3EC] bg-white px-3.5 text-[14px] tracking-[0.04em] text-[#0B2653] outline-none transition placeholder:tracking-normal placeholder:text-[#9AA9BC] focus:border-[#2557E8] focus:ring-4 focus:ring-[#2557E8]/12 dark:border-white/12 dark:bg-[rgba(250,240,230,0.05)] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#B04A5E] dark:focus:ring-[#B04A5E]/20"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="mb-1.5 block text-[12.5px] font-medium"
                  style={{ color: navyColor }}
                >
                  Şifreniz
                </label>
                <div className="relative">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    inputMode="numeric"
                    autoComplete="current-password"
                    maxLength={6}
                    placeholder="6 haneli şifren"
                    value={password}
                    onChange={(e) =>
                      setPassword(e.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    className="h-11 w-full rounded-xl border border-[#DCE3EC] bg-white pl-3.5 pr-11 text-[14px] tracking-[0.04em] text-[#0B2653] outline-none transition placeholder:tracking-normal placeholder:text-[#9AA9BC] focus:border-[#2557E8] focus:ring-4 focus:ring-[#2557E8]/12 dark:border-white/12 dark:bg-[rgba(250,240,230,0.05)] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#B04A5E] dark:focus:ring-[#B04A5E]/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
                    className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-[#7A8CA4] transition hover:bg-[#F1F5FA] hover:text-[#0B2653] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2557E8]/40 dark:text-[#9AACC7] dark:hover:bg-white/10 dark:hover:text-[#EDF1F7]"
                  >
                    {showPassword ? (
                      <EyeOffIcon className="h-[18px] w-[18px]" />
                    ) : (
                      <EyeIcon className="h-[18px] w-[18px]" />
                    )}
                  </button>
                </div>
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={onForgotPassword}
                    style={{ "--accent-dark-link": ACCENT_DARK_LINK } as CSSProperties}
                    className="rounded text-[12.5px] font-medium text-[#5A7292] underline-offset-4 transition hover:text-[#2557E8] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2557E8]/40 dark:text-[var(--accent-dark-link)] dark:hover:text-[#D98A99]"
                  >
                    Şifremi unuttum
                  </button>
                </div>
              </div>

              {error && (
                <p role="alert" className="text-[12.5px] text-[#E63946] dark:text-[#FF8A90]">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={submitted}
                className="group flex h-12 w-full items-center justify-center gap-2 rounded-xl text-[14.5px] font-semibold text-white transition-colors duration-200 hover:enabled:bg-[#1E49C4] focus:outline-none focus-visible:ring-4 focus-visible:ring-[#2557E8]/35 disabled:cursor-not-allowed disabled:opacity-90 dark:hover:enabled:bg-[var(--cta-dark-hover)] dark:focus-visible:ring-[var(--cta-dark-hover)]/40"
                style={
                  {
                    backgroundColor: isDark ? CTA_DARK : BRAND,
                    "--cta-dark-hover": CTA_DARK_HOVER,
                  } as CSSProperties
                }
              >
                Vira Et
                <ArrowIcon className="h-[18px] w-[18px] transition-transform duration-200 group-hover:translate-x-0.5" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginScreen;
