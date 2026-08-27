import { useEffect, useMemo, useState } from "react";
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
import { SURVEY_STEPS, type WizardStage } from "@/components/auth/registerSteps";
import { useAuth } from "@/auth/AuthContext";
import {
  fetchSurveyQuestions,
  scoreSurvey,
  type SurveyAnswers,
  type SurveyMatrixAnswer,
  type SurveyQuestions,
  type SurveyResult,
} from "@/api/survey";
import { gecerliTcKimlikNo } from "@/utils/tckn";
import { formatTRY } from "@/utils/format";

/**
 * Hesap açma sihirbazı — giriş kartının İÇİNDE açılır.
 *
 * `PasswordResetCard` ile aynı desen: ayrı bir sayfaya gitmek arka plandaki
 * eseri, kart çerçevesini ve logoyu yeniden kurmak demek olurdu. Yalnızca
 * kartın içeriği değişiyor.
 *
 * AKIŞ: hesap bilgileri → 5 anket adımı → sonuç ve yorum → açılış aktarımı.
 *
 * ANKET NEDEN ZORUNLU: uygunluk kontrolü (`advice_eligibility`) anket puanına
 * dayanıyor; puansız bir kullanıcıda tavsiye katmanı zaten çalışmaz. Sonradan
 * doldurulacak bir anket, yarım yapılandırılmış hesaplar bırakırdı.
 *
 * SORULAR BU DOSYADA YOK. Sunucudan geliyor; metni buraya kopyalamak, config
 * değiştiğinde arayüzün eski soruyu sormaya devam etmesi ve skorun SORULMAYAN
 * bir soruya göre hesaplanması demek olurdu.
 */

interface RegisterCardProps {
  onBack: () => void;
}

/** Matris satırlarının boş hâli — deneyimi olmayan satır "0" ile doldurulur. */
function bosMatris(questions: SurveyQuestions): Record<string, SurveyMatrixAnswer> {
  const d: Record<string, SurveyMatrixAnswer> = {};
  for (const satir of questions.urun_matrisi.satirlar) {
    d[satir.k] = { bilgi: "0", siklik: "0", hacim: "0" };
  }
  return d;
}

export function RegisterCard({ onBack }: RegisterCardProps) {
  const { register } = useAuth();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;
  const accent = isDark ? ACCENT_DARK : BRAND;

  const [stage, setStage] = useState<WizardStage>("hesap");
  const [anketAdimi, setAnketAdimi] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Hesap bilgileri
  const [fullName, setFullName] = useState("");
  const [tckn, setTckn] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Anket
  const [questions, setQuestions] = useState<SurveyQuestions | null>(null);
  const [cevaplar, setCevaplar] = useState<Record<string, string>>({});
  const [matris, setMatris] = useState<Record<string, SurveyMatrixAnswer>>({});
  const [sonuc, setSonuc] = useState<SurveyResult | null>(null);

  // Aktarım
  const [tutar, setTutar] = useState("");

  // Sorular sihirbaz açılır açılmaz çekiliyor: kullanıcı hesap bilgilerini
  // doldururken arka planda gelsin, anket adımına geçtiğinde beklemesin.
  useEffect(() => {
    let iptal = false;
    fetchSurveyQuestions()
      .then((q) => {
        if (iptal) return;
        setQuestions(q);
        setMatris(bosMatris(q));
      })
      .catch(() => {
        if (!iptal) setError("Anket yüklenemedi. Bağlantınızı kontrol edin.");
      });
    return () => {
      iptal = true;
    };
  }, []);

  const adim = SURVEY_STEPS[anketAdimi];

  const toplamAdim = 1 + SURVEY_STEPS.length + 2;
  const mevcutAdim =
    stage === "hesap"
      ? 1
      : stage === "anket"
        ? 2 + anketAdimi
        : stage === "sonuc"
          ? 1 + SURVEY_STEPS.length + 1
          : toplamAdim;

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
    setStage("anket");
  };

  const anketDevam = async () => {
    const eksik = adim.sorular.filter((kod) => !cevaplar[kod]);
    if (eksik.length > 0) {
      // Eksik cevabı 0 puan saymıyoruz: yarım bırakılmış bir anket
      // "Korumacı" profil üretir ve kullanıcı bunu geçerli sanırdı.
      setError("Devam etmek için bu bölümdeki tüm soruları yanıtlayın.");
      return;
    }
    setError(null);

    if (anketAdimi < SURVEY_STEPS.length - 1) {
      setAnketAdimi((i) => i + 1);
      return;
    }

    setBusy(true);
    try {
      const r = await scoreSurvey({ ...cevaplar, E1: matris } as SurveyAnswers);
      setSonuc(r);
      setStage("sonuc");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anket değerlendirilemedi.");
    } finally {
      setBusy(false);
    }
  };

  const anketGeri = () => {
    setError(null);
    if (anketAdimi === 0) setStage("hesap");
    else setAnketAdimi((i) => i - 1);
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
        survey_answers: { ...cevaplar, E1: matris } as SurveyAnswers,
        // Metin olarak gidiyor: sunucu tarafı `Decimal`, kayan noktaya
        // çevirmek büyük tutarlarda kuruş kaybettirir.
        initial_deposit_try: tutarSayi.toFixed(2),
      });
      // Başarılıysa AuthProvider oturumu açar ve App bu ekranı söker.
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
      {/* İlerleme: 18 soruluk bir anket uzun; kullanıcı nerede olduğunu ve
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
      {stage === "anket" && (
        <>
          <h2
            className="mt-4 font-display text-[24px] font-semibold tracking-[-0.015em]"
            style={{ color: navyColor }}
          >
            {adim.baslik}
          </h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-[#5A7292] dark:text-[#B9C4DC]">
            {adim.aciklama}
          </p>

          {questions === null ? (
            <p className="mt-6 text-[13px] text-[#7A8CA4]">Sorular yükleniyor…</p>
          ) : (
            <div className="mt-6 max-h-[46vh] space-y-6 overflow-y-auto pr-1">
              {adim.sorular.map((kod) => {
                const soru = questions.sorular[kod];
                if (!soru) return null;
                return (
                  <fieldset key={kod}>
                    <legend
                      className="mb-2 text-[13.5px] font-medium leading-snug"
                      style={{ color: navyColor }}
                    >
                      {soru.t}
                    </legend>
                    <div className="space-y-1.5">
                      {soru.o.map(([deger, metin]) => {
                        const secili = cevaplar[kod] === deger;
                        return (
                          <label
                            key={deger}
                            className={
                              "flex cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2.5 text-[13px] leading-snug transition " +
                              (secili
                                ? "border-transparent bg-white/90 dark:bg-white/[0.10]"
                                : "border-[#DCE3EC] bg-white/50 hover:bg-white/80 dark:border-transparent dark:bg-white/[0.04] dark:hover:bg-white/[0.08]")
                            }
                            style={secili ? { boxShadow: `inset 0 0 0 1.5px ${accent}` } : undefined}
                          >
                            <input
                              type="radio"
                              name={kod}
                              value={deger}
                              checked={secili}
                              onChange={() => setCevaplar((c) => ({ ...c, [kod]: deger }))}
                              className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#2557E8] dark:accent-[#B04A5E]"
                            />
                            <span className="text-[#334B6B] dark:text-[#C8D3E6]">{metin}</span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                );
              })}

              {adim.matris && (
                <fieldset>
                  <legend
                    className="mb-2 text-[13.5px] font-medium leading-snug"
                    style={{ color: navyColor }}
                  >
                    Hangi ürünleri tanıyorsunuz ve ne sıklıkta işlem yaparsınız?
                  </legend>
                  <p className="mb-3 text-[12px] leading-snug text-[#7A8CA4] dark:text-[#9AACC7]">
                    Deneyiminiz olmayan satırları boş bırakabilirsiniz.
                  </p>
                  <div className="space-y-3">
                    {questions.urun_matrisi.satirlar.map((satir) => (
                      <div
                        key={satir.k}
                        className="rounded-xl border border-[#DCE3EC] bg-white/50 p-3 dark:border-transparent dark:bg-white/[0.04]"
                      >
                        <p
                          className="text-[13px] font-medium"
                          style={{ color: navyColor }}
                        >
                          {satir.n}
                        </p>
                        <p className="mt-0.5 text-[11.5px] leading-snug text-[#7A8CA4] dark:text-[#9AACC7]">
                          {satir.ex}
                        </p>
                        <div className="mt-2.5 grid grid-cols-3 gap-2">
                          {questions.urun_matrisi.sutunlar.map((sutun) => (
                            <label key={sutun.k} className="block">
                              <span className="mb-1 block text-[11px] font-medium text-[#7A8CA4] dark:text-[#9AACC7]">
                                {sutun.l}
                              </span>
                              <select
                                value={
                                  matris[satir.k]?.[sutun.k as keyof SurveyMatrixAnswer] ?? "0"
                                }
                                onChange={(e) =>
                                  setMatris((m) => ({
                                    ...m,
                                    [satir.k]: { ...m[satir.k], [sutun.k]: e.target.value },
                                  }))
                                }
                                className="h-9 w-full rounded-lg border border-[#DCE3EC] bg-white px-2 text-[12.5px] text-[#0B2653] outline-none focus:border-[#2557E8] dark:border-transparent dark:bg-[rgba(240,220,200,0.05)] dark:text-[#EDF1F7]"
                              >
                                {sutun.o.map(([deger, metin]) => (
                                  <option key={deger} value={deger}>
                                    {metin}
                                  </option>
                                ))}
                              </select>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </fieldset>
              )}
            </div>
          )}

          {hataSatiri}

          <button
            type="button"
            onClick={anketDevam}
            disabled={busy || questions === null}
            className={`${birincilButon} mt-5`}
            style={birincilStil}
          >
            {busy
              ? "Değerlendiriliyor…"
              : anketAdimi < SURVEY_STEPS.length - 1
                ? "Devam et"
                : "Profilimi göster"}
          </button>

          <div className="mt-3 flex justify-center">
            <button type="button" onClick={anketGeri} className={geriButon} style={geriStil}>
              Geri
            </button>
          </div>
        </>
      )}

      {/* ---------------------------------------------------------- */}
      {stage === "sonuc" && sonuc && (
        <>
          <h2
            className="mt-4 font-display text-[24px] font-semibold tracking-[-0.015em]"
            style={{ color: navyColor }}
          >
            {sonuc.sonuc_uretildi ? sonuc.profil_adi : "Profil belirlenemedi"}
          </h2>

          {sonuc.sonuc_uretildi && (
            <div className="mt-4 grid grid-cols-3 gap-2">
              {[
                ["Kapasite", sonuc.kapasite],
                ["Tolerans", sonuc.tolerans],
                ["Bilgi", sonuc.bilgi],
              ].map(([etiket, deger]) => (
                <div
                  key={etiket as string}
                  className="rounded-xl border border-[#DCE3EC] bg-white/60 px-3 py-2.5 text-center dark:border-transparent dark:bg-white/[0.05]"
                >
                  <p className="text-[11px] font-medium text-[#7A8CA4] dark:text-[#9AACC7]">
                    {etiket}
                  </p>
                  <p
                    className="font-display text-[19px] font-bold"
                    style={{ color: navyColor }}
                  >
                    {deger}
                  </p>
                </div>
              ))}
            </div>
          )}

          <p className="mt-4 text-[13.5px] leading-relaxed text-[#334B6B] dark:text-[#C8D3E6]">
            {sonuc.yorum}
          </p>

          {/* Sınır bölgesi uyarısı ATLANMIYOR: bant genişliği ~14 puan, tek
              bir cevap bant değiştirebilir. Söylenmezse aynı kişi testi iki
              hafta arayla çözdüğünde farklı sonuç alır ve ürüne güveni
              sarsılır (entegrasyon kılavuzunun açık uyarısı). */}
          {sonuc.sinir_bolgesinde && (
            <p className="mt-3 rounded-xl border border-[#DCE3EC] bg-white/60 px-3.5 py-2.5 text-[12.5px] leading-snug text-[#5A7292] dark:border-transparent dark:bg-white/[0.05] dark:text-[#B9C4DC]">
              Puanınız iki profil bandının sınırına yakın. Tek bir cevabın
              değişmesi profili kaydırabilir; sonucu bir aralık olarak okuyun.
            </p>
          )}

          {sonuc.kurallar
            .filter((k) => !k.durdurucu)
            .map((k) => (
              <p
                key={k.kod}
                className="mt-3 rounded-xl border border-[#DCE3EC] bg-white/60 px-3.5 py-2.5 text-[12.5px] leading-snug text-[#5A7292] dark:border-transparent dark:bg-white/[0.05] dark:text-[#B9C4DC]"
              >
                {k.mesaj}
              </p>
            ))}

          {hataSatiri}

          {sonuc.sonuc_uretildi ? (
            <button
              type="button"
              onClick={() => {
                setError(null);
                setStage("aktarim");
              }}
              className={`${birincilButon} mt-5`}
              style={birincilStil}
            >
              Devam et
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setError(null);
                setSonuc(null);
                setAnketAdimi(0);
                setStage("anket");
              }}
              className={`${birincilButon} mt-5`}
              style={birincilStil}
            >
              Cevapları gözden geçir
            </button>
          )}
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
                setStage("sonuc");
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
