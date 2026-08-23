import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { useTheme } from "@/context/ThemeContext";
import {
  ACCENT_DARK_LINK,
  BRAND,
  CTA_DARK,
  CTA_DARK_HOVER,
  INPUT_CLASS,
  NAVY,
  NAVY_DARK,
} from "@/components/auth/loginPalette";
import { gecerliTcKimlikNo } from "@/utils/tckn";

/**
 * Şifre yenileme akışı — ARAYÜZ TEMSİLİ.
 *
 * ⚠️ SUNUCU TARAFI YOK. Bu akış hiçbir uca istek atmaz ve hiçbir şifreyi
 * DEĞİŞTİRMEZ; ekranların ve adımların nasıl görüneceğini gösterir. Gerçek
 * bir yenileme akışı en az şunları gerektirir ve hiçbiri bu sürümde yok:
 * e-posta gönderimi, tek kullanımlık kodun sunucuda üretilip saklanması,
 * süre ve deneme sayısı sınırı, kodun kullanıldıktan sonra geçersizleşmesi.
 *
 * DEMO SIRASINDA DİKKAT: akış "şifreniz güncellendi" der ama giriş yine ESKİ
 * şifreyle yapılır. Yeni şifreyle giriş denenirse başarısız olur.
 *
 * KOD UZUNLUĞU 6 HANE: tek kullanımlık şifre standartlarının varsayılanı
 * (RFC 4226/6238) ve Türkiye'deki bankacılık pratiğiyle aynı. Kod alanı
 * bilerek şifre alanıyla aynı uzunlukta değil — ikisi farklı şeyler ama
 * her ikisi de 6 hane olduğu için ayrı adımlarda gösteriliyor.
 */

/** Tekrar gönderme sayacı (saniye). Bankacılıkta yaygın olan 180 sn. */
const YENIDEN_GONDER_SANIYE = 180;

const KOD_UZUNLUGU = 6;
const SIFRE_UZUNLUGU = 6;

type Adim = "kimlik" | "kod" | "yeniSifre" | "bitti";

const ADIM_SIRASI: Adim[] = ["kimlik", "kod", "yeniSifre"];

interface PasswordResetCardProps {
  /** Giriş formuna dön. */
  onBack: () => void;
}

function sayaciBicimle(saniye: number): string {
  const dk = Math.floor(saniye / 60);
  const sn = saniye % 60;
  return `${dk}:${String(sn).padStart(2, "0")}`;
}

export function PasswordResetCard({ onBack }: PasswordResetCardProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;

  const [adim, setAdim] = useState<Adim>("kimlik");
  const [tckn, setTckn] = useState("");
  const [kod, setKod] = useState("");
  const [sifre, setSifre] = useState("");
  const [sifreTekrar, setSifreTekrar] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [kalanSaniye, setKalanSaniye] = useState(0);

  // Sayaç yalnızca kod adımında işler; adım değişince durur.
  useEffect(() => {
    if (adim !== "kod" || kalanSaniye <= 0) return;
    const t = window.setTimeout(() => setKalanSaniye((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [adim, kalanSaniye]);

  const kimlikGonder = (e: FormEvent) => {
    e.preventDefault();
    if (!gecerliTcKimlikNo(tckn)) {
      setHata("Geçerli bir T.C. kimlik numarası girin.");
      return;
    }
    setHata(null);
    setKalanSaniye(YENIDEN_GONDER_SANIYE);
    setAdim("kod");
  };

  const koduDogrula = (e: FormEvent) => {
    e.preventDefault();
    if (kod.length !== KOD_UZUNLUGU) {
      setHata(`Doğrulama kodu ${KOD_UZUNLUGU} haneli olmalı.`);
      return;
    }
    setHata(null);
    setAdim("yeniSifre");
  };

  const sifreyiKaydet = (e: FormEvent) => {
    e.preventDefault();
    if (sifre.length !== SIFRE_UZUNLUGU) {
      setHata(`Şifre ${SIFRE_UZUNLUGU} haneli olmalı.`);
      return;
    }
    if (sifre !== sifreTekrar) {
      setHata("Şifreler eşleşmiyor.");
      return;
    }
    setHata(null);
    setAdim("bitti");
  };

  const birincilButon =
    "flex h-12 w-full items-center justify-center rounded-xl text-[14.5px] font-semibold text-white transition-colors duration-200 hover:enabled:bg-[#1E49C4] focus:outline-none focus-visible:ring-4 focus-visible:ring-[#2557E8]/35 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:enabled:bg-[var(--cta-dark-hover)]";
  const butonStili = {
    backgroundColor: isDark ? CTA_DARK : BRAND,
    "--cta-dark-hover": CTA_DARK_HOVER,
  } as CSSProperties;

  const geriBaglantisi = (
    <button
      type="button"
      onClick={onBack}
      style={{ "--accent-dark-link": ACCENT_DARK_LINK } as CSSProperties}
      className="mt-4 w-full rounded text-center text-[12.5px] font-medium text-[#5A7292] underline-offset-4 transition hover:text-[#2557E8] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2557E8]/40 dark:text-[var(--accent-dark-link)] dark:hover:text-[#D98A99]"
    >
      Giriş ekranına dön
    </button>
  );

  return (
    <div>
      {adim !== "bitti" && (
        <>
          <h2
            className="mt-6 font-display text-[29px] font-semibold tracking-[-0.015em]"
            style={{ color: navyColor }}
          >
            Şifreni yenile
          </h2>
          {/* Adım göstergesi: kullanıcı akışın neresinde olduğunu bilsin. */}
          <div className="mt-4 flex items-center gap-1.5" aria-hidden="true">
            {ADIM_SIRASI.map((a) => {
              const gecildi = ADIM_SIRASI.indexOf(a) <= ADIM_SIRASI.indexOf(adim);
              return (
                <span
                  key={a}
                  className="h-1 flex-1 rounded-full transition-colors"
                  style={{
                    backgroundColor: gecildi ? (isDark ? CTA_DARK : BRAND) : "#DCE3EC",
                  }}
                />
              );
            })}
          </div>
        </>
      )}

      {adim === "kimlik" && (
        <form onSubmit={kimlikGonder} className="mt-5 space-y-4" noValidate>
          <p className="m-0 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            Kayıtlı T.C. kimlik numaranı gir; e-posta adresine {KOD_UZUNLUGU} haneli bir
            doğrulama kodu gönderelim.
          </p>
          <div>
            <label
              htmlFor="reset-tckn"
              className="mb-1.5 block text-[12.5px] font-medium"
              style={{ color: navyColor }}
            >
              T.C. Kimlik Numaranız
            </label>
            <input
              id="reset-tckn"
              inputMode="numeric"
              autoComplete="username"
              autoFocus
              maxLength={11}
              placeholder="11 haneli kimlik numaran"
              value={tckn}
              onChange={(e) => setTckn(e.target.value.replace(/\D/g, "").slice(0, 11))}
              className={INPUT_CLASS}
            />
          </div>
          {hata && (
            <p role="alert" className="text-[12.5px] text-[#E63946] dark:text-[#FF8A90]">
              {hata}
            </p>
          )}
          <button type="submit" className={birincilButon} style={butonStili}>
            Doğrulama kodu gönder
          </button>
          {geriBaglantisi}
        </form>
      )}

      {adim === "kod" && (
        <form onSubmit={koduDogrula} className="mt-5 space-y-4" noValidate>
          <p className="m-0 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            Kayıtlı e-posta adresine {KOD_UZUNLUGU} haneli bir doğrulama kodu gönderdik.
            Kod {sayaciBicimle(YENIDEN_GONDER_SANIYE)} boyunca geçerlidir.
          </p>
          <div>
            <label
              htmlFor="reset-kod"
              className="mb-1.5 block text-[12.5px] font-medium"
              style={{ color: navyColor }}
            >
              Doğrulama Kodu
            </label>
            <input
              id="reset-kod"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              maxLength={KOD_UZUNLUGU}
              placeholder={`${KOD_UZUNLUGU} haneli kod`}
              value={kod}
              onChange={(e) => setKod(e.target.value.replace(/\D/g, "").slice(0, KOD_UZUNLUGU))}
              className={`${INPUT_CLASS} text-center text-[18px] tracking-[0.5em]`}
            />
          </div>
          <div className="flex items-center justify-between text-[12.5px]">
            <span className="text-[#5A7292] dark:text-[#B9C4DC]">
              {kalanSaniye > 0 ? `Kalan süre ${sayaciBicimle(kalanSaniye)}` : "Kodun süresi doldu"}
            </span>
            <button
              type="button"
              disabled={kalanSaniye > 0}
              onClick={() => {
                setKod("");
                setHata(null);
                setKalanSaniye(YENIDEN_GONDER_SANIYE);
              }}
              className="font-medium text-[#2557E8] underline-offset-4 transition hover:underline disabled:cursor-not-allowed disabled:text-[#9AA9BC] disabled:no-underline dark:text-[var(--accent-dark-link)]"
              style={{ "--accent-dark-link": ACCENT_DARK_LINK } as CSSProperties}
            >
              Tekrar gönder
            </button>
          </div>
          {hata && (
            <p role="alert" className="text-[12.5px] text-[#E63946] dark:text-[#FF8A90]">
              {hata}
            </p>
          )}
          <button type="submit" className={birincilButon} style={butonStili}>
            Doğrula
          </button>
          {geriBaglantisi}
        </form>
      )}

      {adim === "yeniSifre" && (
        <form onSubmit={sifreyiKaydet} className="mt-5 space-y-4" noValidate>
          <p className="m-0 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            Yeni şifren {SIFRE_UZUNLUGU} haneli ve yalnızca rakamlardan oluşmalı.
          </p>
          <div>
            <label
              htmlFor="reset-sifre"
              className="mb-1.5 block text-[12.5px] font-medium"
              style={{ color: navyColor }}
            >
              Yeni Şifreniz
            </label>
            <input
              id="reset-sifre"
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              autoFocus
              maxLength={SIFRE_UZUNLUGU}
              placeholder={`${SIFRE_UZUNLUGU} haneli şifre`}
              value={sifre}
              onChange={(e) =>
                setSifre(e.target.value.replace(/\D/g, "").slice(0, SIFRE_UZUNLUGU))
              }
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label
              htmlFor="reset-sifre-tekrar"
              className="mb-1.5 block text-[12.5px] font-medium"
              style={{ color: navyColor }}
            >
              Yeni Şifreniz (Tekrar)
            </label>
            <input
              id="reset-sifre-tekrar"
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              maxLength={SIFRE_UZUNLUGU}
              placeholder="Şifreni tekrar gir"
              value={sifreTekrar}
              onChange={(e) =>
                setSifreTekrar(e.target.value.replace(/\D/g, "").slice(0, SIFRE_UZUNLUGU))
              }
              className={INPUT_CLASS}
            />
          </div>
          {hata && (
            <p role="alert" className="text-[12.5px] text-[#E63946] dark:text-[#FF8A90]">
              {hata}
            </p>
          )}
          <button type="submit" className={birincilButon} style={butonStili}>
            Şifreyi güncelle
          </button>
          {geriBaglantisi}
        </form>
      )}

      {adim === "bitti" && (
        <div className="mt-6">
          <span
            className="grid h-12 w-12 place-items-center rounded-full"
            style={{ backgroundColor: isDark ? "rgba(107,33,48,0.35)" : "#E8F0FE" }}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke={isDark ? "#D98A99" : BRAND}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-6 w-6"
            >
              <path d="M20 6 9 17l-5-5" />
            </svg>
          </span>
          <h2
            className="mt-5 font-display text-[29px] font-semibold tracking-[-0.015em]"
            style={{ color: navyColor }}
          >
            Şifren güncellendi
          </h2>
          <p className="mt-2 text-[13.5px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            Yeni şifrenle giriş yapabilirsin.
          </p>
          <button
            type="button"
            onClick={onBack}
            className={`${birincilButon} mt-6`}
            style={butonStili}
          >
            Giriş ekranına dön
          </button>
        </div>
      )}
    </div>
  );
}
