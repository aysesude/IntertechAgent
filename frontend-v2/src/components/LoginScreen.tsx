import { useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import {
  ACCENT_DARK,
  ACCENT_DARK_ICON,
  ACCENT_DARK_LINK,
  BRAND,
  CTA_DARK,
  CTA_DARK_HOVER,
  INPUT_CLASS,
  NAVY,
  NAVY_DARK,
} from "@/components/auth/loginPalette";
import { PasswordResetCard } from "@/components/auth/PasswordResetCard";
import { RegisterCard } from "@/components/auth/RegisterCard";
import { SurveyGate } from "@/components/survey/SurveyGate";
import { PaperBoatLogo } from "@/components/paper-boat/PaperBoat";
import { gecerliTcKimlikNo } from "@/utils/tckn";

/**
 * LoginScreen — "Finansal rotanı birlikte çizelim."
 *
 * Arka plan sanat eseri: light modda Halit, "Boğaziçi Yalıları", 1920
 * (yağlıboya) — görsel hiçbir şekilde manipüle edilmiyor, sadece
 * okunabilirlik için üstüne çok hafif beyaz gradient katmanları biniyor.
 * Dark modda ayrı bir tablo (ay ışığında deniz) kullanılıyor; görsel
 * kendisi manipüle edilmiyor, üstüne düz/yönsüz %38 opaklıkta bir siyah
 * katman + sol tarafı biraz daha koyultan ince bir soldan-sağa gradyan
 * biniyor (bkz. resolvedTheme'e göre seçilen backgroundArt).
 *
 * Asset:  src/assets/login/bogazici-yalilari.jpg (light)
 *         src/assets/login/ay-isigi-deniz.jpg (dark)
 * Logo:   gemi `components/paper-boat` bileşeninden (sohbettekiyle aynı,
 *         sallanan hâliyle), yazı `public/vira_wordmark.svg` — ikisi de
 *         özgün `vira_logo_text.svg`'nin parçaları, çizim değiştirilmedi.
 */
import bosphorusArt from "../assets/login/bogazici-yalilari.jpg";
import moonlitSeaArt from "../assets/login/ay-isigi-deniz.jpg";

/* ------------------------------------------------------------------ */
/*  Sabitler                                                           */
/* ------------------------------------------------------------------ */

// Palet ayrı dosyada: giriş kartı ile şifre yenileme kartı aynı renkleri
// kullanıyor, iki yerde kopyalanırsa biri değiştiğinde diğeri sessizce ayrışır.
// BRAND_DARK geriye dönük uyumluluk için buradan da dışa aktarılıyor.
export { BRAND_DARK } from "@/components/auth/loginPalette";


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
          className="flex h-full flex-col justify-start rounded-2xl border border-transparent bg-white/[0.40] px-4 py-3.5 shadow-[0_8px_28px_-16px_rgba(11,38,83,0.45)] backdrop-blur-[16px] dark:bg-[#07111c]/[0.45] dark:shadow-[0_8px_28px_-18px_rgba(0,0,0,0.55)]"
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
  /**
   * Giriş ekranına düşme sebebi (ör. oturum süresi doldu). Kullanıcı sessizce
   * atılmasın diye gösteriliyor.
   */
  notice?: string | null;
  /**
   * Kimlik bilgilerini doğrular. Reddedilirse (sunucu 401 verirse) hata
   * mesajı formda gösterilir ve alanlar tekrar denenebilir hale gelir.
   *
   * `void` DEĞİL `Promise<void>`: giriş artık ağa çıkıyor ve butonun ne
   * zaman "çözüleceğini" yalnızca sonucu bekleyerek bilebiliriz.
   */
  onSubmit?: (credentials: { tckn: string; password: string }) => Promise<void> | void;
  /**
   * Dolu ise kart giriş formu yerine ANKETİ çizer.
   *
   * Anket bir süre ayrı bir tam sayfaydı; kullanıcı "üye ol"dan sonra
   * bambaşka bir ekrana düşmüş gibi oluyordu. Aynı kartın içinde açılması
   * için bu ekran ondan sorumlu — arka plandaki eseri, kart çerçevesini ve
   * logoyu ikinci kez kurmanın anlamı yok.
   *
   * Kullanıcı BURADA GİRİŞ YAPMIŞ DURUMDA; ekran yalnızca kabuğu ödünç
   * veriyor. Bu yüzden `onSubmit`/`notice` bu modda kullanılmaz.
   */
  anket?: { userId: string; fullName: string } | null;
};

export function LoginScreen({
  onSubmit,
  notice = null,
  anket = null,
}: LoginScreenProps) {
  // "login" | "reset" | "register" — üçü de aynı kartın içinde açılıyor;
  // ayrı bir sayfaya gitmek arka plandaki eseri ve kart çerçevesini
  // yeniden kurmak demek olurdu. Anket de aynı kartta, ama modu içeriden
  // değil dışarıdan geliyor: o adıma kullanıcının puanı olmadığı için
  // girilir, bir düğmeye basıldığı için değil.
  const [mod, setMod] = useState<"login" | "reset" | "register">("login");
  const [submitted, setSubmitted] = useState(false);
  const [tckn, setTckn] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (submitted) return;
    // İstemci doğrulaması yalnızca kullanıcı konforu içindir; asıl kapı
    // sunucudadır (backend/app/schemas/auth.py).
    // Yalnızca BİÇİM kontrolü (11 hane, rakam). Sağlama doğrulaması bilerek
    // yok — gerekçesi utils/tckn.ts başlığında.
    if (!gecerliTcKimlikNo(tckn)) {
      setError("T.C. kimlik numarası 11 haneli olmalı.");
      return;
    }
    if (password.length !== 6) {
      setError("Şifre 6 haneli olmalı.");
      return;
    }
    setError(null);
    setSubmitted(true);
    try {
      await onSubmit?.({ tckn, password });
      // Başarılıysa `submitted` true kalır: bu bileşen birazdan unmount
      // olacak (App'teki crossfade) ve bu arada ikinci gönderim olmamalı.
    } catch (err) {
      // Sunucunun Türkçe mesajı doğrudan gösterilir ("T.C. kimlik numarası
      // veya şifre hatalı." gibi) — bu metinler kullanıcıya gösterilmek
      // üzere yazılmıştır.
      setError(err instanceof Error ? err.message : "Giriş yapılamadı.");
      setSubmitted(false);
    }
  };

  return (
    <div className="relative min-h-[100dvh] w-full overflow-hidden bg-[#EAF0F7] dark:bg-[#0A0F16]">
      {/* --- Tablo: light modda değiştirilmedi, sadece cover. Dark modda ayrı
          bir eser (ay ışığında deniz) — dashboard'daki gibi silik bir doku
          değil, yüksek görünürlükte (opaklık ~1) ana görsel. --- */}
      <img
        src={isDark ? moonlitSeaArt : bosphorusArt}
        alt={isDark ? "" : "Halit, Boğaziçi Yalıları, 1920"}
        className="absolute inset-0 h-full w-full object-cover"
        style={{
          objectPosition: `${OBJECT_POS_X * 100}% ${OBJECT_POS_Y * 100}%`,
          zIndex: Z_LAYER.background,
        }}
        draggable={false}
      />

      {/* --- Dark modda görselin tamamına EŞİT, çok hafif bir siyah katman —
          yön/vinyet yok (o zaman görsel "bozulmuş" hissettiriyordu), sadece
          düz %38 opaklıkla dark tema zeminine biraz daha yakınlaştırıyor. --- */}
      {isDark && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{ backgroundColor: "rgba(4,7,12,0.38)", zIndex: Z_LAYER.background }}
        />
      )}

      {/* --- Sol taraf (başlık/form bölgesi) bir tık daha koyu — hafif bir
          soldan-sağa gradyan, üstteki düz katmana ek olarak biniyor. --- */}
      {isDark && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, rgba(4,7,12,0.18) 0%, rgba(4,7,12,0.06) 32%, rgba(4,7,12,0) 55%)",
            zIndex: Z_LAYER.background,
          }}
        />
      )}

      {/* --- Okunabilirlik katmanları (çok hafif) — SADECE light mod, hiç
          değiştirilmedi. Dark modda yukarıdaki düz katman var. --- */}
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

      {/* --- Eser künyesi: arka plandaki tabloya ait, sağ alt köşede — çok
          küçük ve düşük kontrastlı, arka planla bütünleşsin diye bilerek
          dikkat çekmiyor. pointer-events-none: salt dekoratif, tıklamayı
          engellemesin. Sol üstteki başlık/kart alanlarından uzak durduğu
          için hiçbir içerikle çakışmıyor; max-w ile mobilde de taşmıyor.
          text-shadow: görsel doğrudan altında olduğu için (kart/zemin değil)
          okunabilirlik payı — light'ta beyaz halo, dark'ta siyah halo. --- */}
      <p
        className="pointer-events-none absolute bottom-3 right-4 max-w-[62%] text-right text-[9px] font-medium leading-snug tracking-wide text-[#4A6488]/60 dark:text-[#9AACC7]/70 sm:bottom-4 sm:right-6 sm:max-w-[46%] sm:text-[10px]"
        style={{
          zIndex: Z_LAYER.background + 1,
          textShadow: isDark
            ? "0 1px 3px rgba(0,0,0,0.6)"
            : "0 1px 3px rgba(255,255,255,0.55)",
        }}
      >
        {isDark
          ? "Arkhip İvanoviç Kuinci — Лунная ночь (Ay Işığında Gece)"
          : "Halit Paşa — Boğaziçi Yalıları"}
      </p>

      {/* --- Tema toggle: Header login ekranında görünmüyor, bu yüzden
          burada küçük, sabit boyutlu bir düğme var — mevcut hiçbir öğeyle
          çakışmayan sağ üst köşede. --- */}
      <button
        type="button"
        onClick={() => setTheme(isDark ? "light" : "dark")}
        aria-label={isDark ? "Açık temaya geç" : "Koyu temaya geç"}
        className="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full border border-white/70 bg-white/80 text-[#0B2653] shadow-[0_6px_20px_-12px_rgba(11,38,83,0.5)] backdrop-blur-sm transition-colors hover:bg-white lg:right-8 lg:top-7 dark:border-transparent dark:bg-white/10 dark:text-[#DCE6FA] dark:hover:bg-white/20"
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
          </div>
        </div>

        {/* Sağ: login kartı */}
        <div className="flex items-center justify-center lg:justify-end lg:py-10 lg:pr-6">
          {/* Koyu temada zemin artık soldan sağa eriyen bir gradient (düz
              renk DEĞİL): sol/orta (form içeriği) okunur kalırken, kartın
              sağ kenarı tamamen şeffaflaşıp arka plan tablosuyla kaynaşıyor
              — kutu orada fark edilmesin diye kasıtlı. Gölge de aynı sebeple
              yumuşatıldı, aksi halde şeffaf kenarda bile kutunun silueti
              gölgeden belli olurdu. */}
          <div
            data-login-card
            /* Kayıt modunda kart genişliyor: anket 18 soru ve 5×3'lük bir
               ürün matrisi taşıyor, 452 pikselde seçenek metinleri üç satıra
               kırılıyordu. Koyu temadaki sağa doğru eriyen zemin de bu
               genişlikte korunuyor. */
            className={`w-full rounded-[26px] border border-white/70 bg-white/[0.45] p-7 backdrop-blur-2xl shadow-[0_28px_70px_-30px_rgba(11,38,83,0.45),0_2px_10px_-4px_rgba(11,38,83,0.12)] dark:border-transparent dark:bg-transparent dark:bg-[linear-gradient(to_right,rgba(7,17,28,0.45)_0%,rgba(7,17,28,0.45)_55%,rgba(7,17,28,0.15)_80%,rgba(7,17,28,0)_100%)] dark:shadow-[0_28px_70px_-30px_rgba(0,0,0,0.3)] sm:p-8 ${
              anket || mod === "register" ? "max-w-[560px]" : "max-w-[452px]"
            }`}
          >
            {/* LOGO İKİ PARÇA ÇİZİLİYOR: gemi + yazı.
                Tek bir `<img>` olduğu sürece gemiye can veremiyorduk —
                sohbetteki sallanma, çizimin gövde/yelken/dalga gruplarını ayrı
                ayrı hareket ettiriyor ve bunun için SVG'nin DOM'da olması
                gerekiyor. Gemi artık sohbettekiyle AYNI bileşen
                (`components/paper-boat`), yazı ise özgün logodan kırpılmış
                `vira_wordmark.svg`.

                Sohbettekinden daha yavaş ve daha küçük genlikte: orada hareket
                "cevap yazılıyor" demek, burada sadece ekranı canlı tutuyor.
                Hızlı sallanan bir marka, okunmakta olan formdan dikkat
                çalardı. */}
            {/* ORANLAR ÖZGÜN LOGODAN ÖLÇÜLDÜ, göz kararı seçilmedi:
                yazı yüksekliği geminin %59'u, aradaki boşluk gemi
                yüksekliğinin %10'u, yazının merkezi geminin merkezinden
                3px yukarıda. Gemi 70px genişlikte ≈ 44px yüksekliğinde
                (özgün logonun `h-11` hâliyle aynı). */}
            <div className="flex items-center gap-1">
              <PaperBoatLogo
                size={70}
                sailing
                speed={0.5}
                amplitude={0.7}
                style={{ color: navyColor }}
              />
              <img
                src="/vira_wordmark.svg"
                alt="Vira"
                className="h-[26px] w-auto -translate-y-[3px] dark:[filter:brightness(0)_invert(1)]"
                draggable={false}
              />
            </div>

            {/* Şifre yenileme aynı kartın İÇİNDE açılıyor: ayrı bir sayfaya
                gitmek arka plandaki eseri, kart çerçevesini ve logoyu yeniden
                kurmak demek olurdu. Yalnızca kartın içeriği değişiyor. */}
            {anket ? (
              <SurveyGate userId={anket.userId} fullName={anket.fullName} />
            ) : mod === "reset" ? (
              <PasswordResetCard onBack={() => setMod("login")} />
            ) : mod === "register" ? (
              <RegisterCard onBack={() => setMod("login")} />
            ) : (
            <>
            <h2
              className="mt-6 font-display text-[29px] font-semibold tracking-[-0.015em]"
              style={{ color: navyColor }}
            >
              Tekrar hoş geldin
            </h2>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
              Hesabına giriş yaparak finansal rotana devam et.
            </p>

            {/* Oturum süresi dolduğunda kullanıcı sessizce buraya atılıyordu;
                neden atıldığını söylemek zorundayız. */}
            {notice && (
              <p
                role="status"
                className="mt-4 rounded-xl border border-[#DCE3EC] bg-white/70 px-3.5 py-2.5 text-[12.5px] text-[#5A7292] dark:border-transparent dark:bg-white/[0.06] dark:text-[#B9C4DC]"
              >
                {notice}
              </p>
            )}

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
                  autoFocus
                  maxLength={11}
                  placeholder="11 haneli kimlik numaran"
                  value={tckn}
                  onChange={(e) =>
                    setTckn(e.target.value.replace(/\D/g, "").slice(0, 11))
                  }
                  className={INPUT_CLASS}
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
                    /* INPUT_CLASS ile aynı, tek farkı sağdaki göz butonuna yer
                       açan `pr-11` dolgusu — Tailwind'de sınıf sırası çakışmayı
                       çözmediği için burada tam sınıf yazılıyor. */
                    className="h-11 w-full rounded-xl border border-[#DCE3EC] bg-white pl-3.5 pr-11 text-[14px] tracking-[0.04em] text-[#0B2653] outline-none transition placeholder:tracking-normal placeholder:text-[#9AA9BC] focus:border-[#2557E8] focus:ring-4 focus:ring-[#2557E8]/12 dark:border-transparent dark:bg-[rgba(250,240,230,0.05)] dark:text-[#EDF1F7] dark:placeholder:text-[#7C8AA6] dark:focus:border-[#B04A5E] dark:focus:ring-[#B04A5E]/20"
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
                    onClick={() => {
                      setError(null);
                      setMod("reset");
                    }}
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
                {submitted ? "Giriş yapılıyor…" : "Giriş Yap"}
                <ArrowIcon className="h-[18px] w-[18px] transition-transform duration-200 group-hover:translate-x-0.5" />
              </button>

              {/* Hesabı olmayan kullanıcının tek çıkış yolu buydu: demo
                  kullanıcıları `make seed` ile üretiliyordu ve dışarıdan
                  gelen biri sisteme hiç giremiyordu. */}
              <div className="flex items-center justify-center gap-1.5 pt-1">
                <span className="text-[12.5px] text-[#5A7292] dark:text-[#B9C4DC]">
                  Hesabın yok mu?
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setMod("register");
                  }}
                  style={{ "--accent-dark-link": ACCENT_DARK_LINK } as CSSProperties}
                  className="rounded text-[12.5px] font-semibold underline-offset-4 transition hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2557E8]/40 dark:text-[var(--accent-dark-link)] dark:hover:text-[#D98A99]"
                >
                  <span style={{ color: isDark ? undefined : BRAND }}>Üye ol</span>
                </button>
              </div>
            </form>
            </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginScreen;
