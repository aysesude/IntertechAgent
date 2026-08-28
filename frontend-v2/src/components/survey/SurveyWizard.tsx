import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { useTheme } from "@/context/ThemeContext";
import {
  ACCENT_DARK,
  ACCENT_DARK_LINK,
  BRAND,
  CTA_DARK,
  CTA_DARK_HOVER,
  NAVY,
  NAVY_DARK,
} from "@/components/auth/loginPalette";
import { SURVEY_STEPS } from "@/components/auth/registerSteps";
import {
  fetchSurveyQuestions,
  type SurveyAnswers,
  type SurveyMatrixAnswer,
  type SurveyQuestions,
  type SurveyResult,
} from "@/api/survey";

/**
 * Yatırımcı risk profili anketi — beş bölümlük sihirbaz + sonuç ekranı.
 *
 * NEREDEN ÇAĞRILIYOR: yalnızca ilk girişte, `SurveyGate` üzerinden. Anket
 * eskiden kayıt akışının içindeydi; 18 soru + matris hesabın hiç açılmamasına
 * yol açtığı için ayrıldı (kayıt artık iki adım). Bileşen o yüzden kendi
 * kabuğunu çizmiyor — çağıran taraf kartı/kaplamayı kuruyor.
 *
 * SORULAR BURADA YOK, sunucudan geliyor. Metni buraya kopyalamak, config
 * değiştiğinde arayüzün eski soruyu sormaya devam etmesi ve skorun
 * SORULMAYAN bir soruya göre hesaplanması demek olurdu.
 *
 * SKORLAMA DA BURADA DEĞİL: cevaplar `onSubmit` ile dışarı verilir, çağıran
 * taraf sunucuya gönderir. İstemcide skorlamak, herkesin kendini "Agresif"
 * ilan edebilmesi demekti.
 */

interface SurveyWizardProps {
  /** Cevapları sunucuya gönderir ve sonucu döndürür. */
  onSubmit: (answers: SurveyAnswers) => Promise<SurveyResult>;
  /** Sonuç ekranındaki onay düğmesine basıldığında. */
  onDone: (sonuc: SurveyResult) => void;
  /** Sonuç ekranındaki birincil düğmenin metni. */
  bitirButonMetni?: string;
  /** Üstte "Adım n / m" göstergesi çizilsin mi? */
  ilerlemeGoster?: boolean;
  /** Geri düğmesi ilk adımda bunu çağırır; verilmezse düğme çizilmez. */
  onIlkAdimdaGeri?: () => void;
}

function bosMatris(questions: SurveyQuestions): Record<string, SurveyMatrixAnswer> {
  const d: Record<string, SurveyMatrixAnswer> = {};
  for (const satir of questions.urun_matrisi.satirlar) {
    d[satir.k] = { bilgi: "0", siklik: "0", hacim: "0" };
  }
  return d;
}

export function SurveyWizard({
  onSubmit,
  onDone,
  bitirButonMetni = "Devam et",
  ilerlemeGoster = true,
  onIlkAdimdaGeri,
}: SurveyWizardProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const navyColor = isDark ? NAVY_DARK : NAVY;
  const accent = isDark ? ACCENT_DARK : BRAND;

  const [adimIndex, setAdimIndex] = useState(0);
  const [questions, setQuestions] = useState<SurveyQuestions | null>(null);
  const [cevaplar, setCevaplar] = useState<Record<string, string>>({});
  const [matris, setMatris] = useState<Record<string, SurveyMatrixAnswer>>({});
  const [sonuc, setSonuc] = useState<SurveyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const adim = SURVEY_STEPS[adimIndex];
  const toplamAdim = SURVEY_STEPS.length + 1;
  const mevcutAdim = sonuc ? toplamAdim : adimIndex + 1;

  const devam = async () => {
    const eksik = adim.sorular.filter((kod) => !cevaplar[kod]);
    if (eksik.length > 0) {
      // Eksik cevabı 0 puan saymıyoruz: yarım bırakılmış bir anket
      // "Korumacı" profil üretir ve kullanıcı bunu geçerli sanırdı.
      setError("Devam etmek için bu bölümdeki tüm soruları yanıtlayın.");
      return;
    }
    setError(null);

    if (adimIndex < SURVEY_STEPS.length - 1) {
      setAdimIndex((i) => i + 1);
      return;
    }

    setBusy(true);
    try {
      setSonuc(await onSubmit({ ...cevaplar, E1: matris } as SurveyAnswers));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anket değerlendirilemedi.");
    } finally {
      setBusy(false);
    }
  };

  const geri = () => {
    setError(null);
    if (adimIndex === 0) onIlkAdimdaGeri?.();
    else setAdimIndex((i) => i - 1);
  };

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

  /* ------------------------------------------------------------------ */
  /*  Sonuç ekranı                                                       */
  /* ------------------------------------------------------------------ */
  if (sonuc) {
    return (
      <div>
        {ilerlemeGoster && <Ilerleme mevcut={toplamAdim} toplam={toplamAdim} renk={accent} isDark={isDark} />}

        <h2
          className="mt-4 font-display text-[24px] font-semibold tracking-[-0.015em]"
          style={{ color: navyColor }}
        >
          {sonuc.sonuc_uretildi ? sonuc.profil_adi : "Profil belirlenemedi"}
        </h2>

        {/* DURDURUCU KURALIN MESAJI EN ÜSTTE. Bu blok eskiden hiç
            gösterilmiyordu (kurallar `!k.durdurucu` ile süzülüyordu) ve
            kullanıcı "cevaplarınız çelişiyor" diyen genel bir metinle
            kapatılamaz ekranda kalıyordu — hangi iki cevabı düzelteceğini
            bilmeden. Sunucu kuralı zaten döndürüyor; tek eksik onu
            göstermekti. */}
        {sonuc.kurallar
          .filter((k) => k.durdurucu)
          .map((k) => (
            <p
              key={k.kod}
              role="alert"
              className="mt-4 rounded-xl border border-[#E63946]/30 bg-[#E63946]/[0.06] px-3.5 py-3 text-[13px] leading-snug text-[#8C2F38] dark:border-[#FF8A90]/25 dark:bg-[#FF8A90]/[0.08] dark:text-[#FFB3B7]"
            >
              {k.mesaj}
            </p>
          ))}

        {sonuc.sonuc_uretildi && (
          <div className="mt-4 grid grid-cols-3 gap-2">
            {(
              [
                ["Kapasite", sonuc.kapasite],
                ["Tolerans", sonuc.tolerans],
                ["Bilgi", sonuc.bilgi],
              ] as const
            ).map(([etiket, deger]) => (
              <div
                key={etiket}
                className="rounded-xl border border-[#DCE3EC] bg-white/60 px-3 py-2.5 text-center dark:border-transparent dark:bg-white/[0.05]"
              >
                <p className="text-[11px] font-medium text-[#7A8CA4] dark:text-[#9AACC7]">
                  {etiket}
                </p>
                <p className="font-display text-[19px] font-bold" style={{ color: navyColor }}>
                  {deger}
                </p>
              </div>
            ))}
          </div>
        )}

        <p className="mt-4 text-[13.5px] leading-relaxed text-[#334B6B] dark:text-[#C8D3E6]">
          {sonuc.yorum}
        </p>

        {/* Sınır bölgesi uyarısı ATLANMIYOR: bant genişliği ~14 puan, tek bir
            cevap bant değiştirebilir. Söylenmezse aynı kişi testi iki hafta
            arayla çözdüğünde farklı sonuç alır ve ürüne güveni sarsılır. */}
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

        {sonuc.sonuc_uretildi ? (
          <button
            type="button"
            onClick={() => onDone(sonuc)}
            className={`${birincilButon} mt-5`}
            style={birincilStil}
          >
            {bitirButonMetni}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => {
              setSonuc(null);
              setAdimIndex(0);
              setError(null);
            }}
            className={`${birincilButon} mt-5`}
            style={birincilStil}
          >
            Cevapları gözden geçir
          </button>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------ */
  /*  Soru adımları                                                      */
  /* ------------------------------------------------------------------ */
  return (
    <div>
      {ilerlemeGoster && <Ilerleme mevcut={mevcutAdim} toplam={toplamAdim} renk={accent} isDark={isDark} />}

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
        <div className="mt-6 max-h-[52vh] space-y-6 overflow-y-auto pr-1">
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
                    <p className="text-[13px] font-medium" style={{ color: navyColor }}>
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
                            value={matris[satir.k]?.[sutun.k as keyof SurveyMatrixAnswer] ?? "0"}
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
        onClick={devam}
        disabled={busy || questions === null}
        className={`${birincilButon} mt-5`}
        style={birincilStil}
      >
        {busy
          ? "Değerlendiriliyor…"
          : adimIndex < SURVEY_STEPS.length - 1
            ? "Devam et"
            : "Profilimi göster"}
      </button>

      {(adimIndex > 0 || onIlkAdimdaGeri) && (
        <div className="mt-3 flex justify-center">
          <button type="button" onClick={geri} className={geriButon} style={geriStil}>
            Geri
          </button>
        </div>
      )}
    </div>
  );
}

function Ilerleme({
  mevcut,
  toplam,
  renk,
  isDark,
}: {
  mevcut: number;
  toplam: number;
  renk: string;
  isDark: boolean;
}) {
  return (
    <>
      <div className="flex items-center gap-2">
        {Array.from({ length: toplam }, (_, i) => (
          <span
            key={i}
            className="h-1 flex-1 rounded-full transition-colors"
            style={{
              backgroundColor: i < mevcut ? renk : isDark ? "rgba(255,255,255,0.14)" : "#DCE3EC",
            }}
          />
        ))}
      </div>
      <p className="mt-2 text-[11.5px] font-medium text-[#7A8CA4] dark:text-[#9AACC7]">
        Adım {mevcut} / {toplam}
      </p>
    </>
  );
}

export default SurveyWizard;
