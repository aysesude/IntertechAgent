import { useMemo, useState } from "react";
import { PageHeading } from "@/components/common/PageHeading";
import { Card } from "@/components/common/Card";
import { Button } from "@/components/common/Button";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { AssetLogo } from "@/components/common/AssetLogo";
import { TradePanel } from "@/components/trade/TradePanel";
import { useTradeData } from "@/hooks/useTradeData";
import { useCurrentUserId } from "@/auth/AuthContext";
import { depositCash, type ApiTradableAsset, type ApiTradeSide } from "@/api/trade";
import { formatNumberTR, formatTRY, formatTRY2 } from "@/utils/format";
import { INVESTMENT_DISCLAIMER } from "@/data/mockData";

/**
 * Al/Sat ekranı.
 *
 * Portföyün üstünde bir "ne olurdu" katmanı değil: buradaki her onay
 * defterin kendisine kayıt düşüyor ve portföy ekranı anında değişiyor.
 *
 * AL SEKMESİNDE YALNIZCA ALINABİLİR VARLIKLAR LİSTELENİR (28 Ağustos 2026
 * ürün kararı). Önce kilitli gösteriliyorlardı; listenin büyük kısmı
 * tıklanamaz satırdan oluşunca ekran kullanıcının yapabileceği şeyi
 * gizler hale geldi. Gizlenenlerin VARLIĞI yine söyleniyor — listenin
 * altındaki tek satır kaç tanesinin neden düştüğünü yazar, yoksa kullanıcı
 * aradığı varlığı bulamayıp sistemi arızalı sanardı.
 *
 * Uç TAM LİSTEYİ dönmeye devam ediyor; eleme burada. Sayıyı hesaplayabilmek
 * de, ileride "puanınızı yükseltirseniz şunlar açılır" ekranı da buna bağlı.
 */

const SINIF_ETIKETLERI: Record<string, string> = {
  stock: "Hisse",
  bond: "Tahvil/Fon",
  currency: "Döviz",
  precious_metal: "Kıymetli Maden",
  cash: "Nakit",
};

const SINIF_FILTRELERI = ["Tümü", "stock", "precious_metal", "currency", "bond"] as const;

export function TradePage() {
  const userId = useCurrentUserId();
  const { data, loading, error, refetch } = useTradeData();
  const [sekme, setSekme] = useState<ApiTradeSide>("buy");
  const [arama, setArama] = useState("");
  const [sinif, setSinif] = useState<(typeof SINIF_FILTRELERI)[number]>("Tümü");
  const [secili, setSecili] = useState<ApiTradableAsset | null>(null);
  const [bildirim, setBildirim] = useState<string | null>(null);
  const [yatiriliyor, setYatiriliyor] = useState(false);

  const { varliklar, gizlenen } = useMemo(() => {
    const hepsi = data?.assets ?? [];
    // SAT sekmesinde yalnızca elindekiler: satılamayacak varlıkları
    // listelemek, tıklanınca "elinizde yok" hatası vermekten kötü.
    const temel = sekme === "sell" ? hepsi.filter((a) => a.held_quantity > 0) : hepsi;
    const q = arama.trim().toLocaleLowerCase("tr");
    const suzulmus = temel.filter(
      (a) =>
        (sinif === "Tümü" || a.asset_class === sinif) &&
        (q === "" ||
          a.symbol.toLocaleLowerCase("tr").includes(q) ||
          a.name.toLocaleLowerCase("tr").includes(q)),
    );
    // Gizlenen sayısı ARAMA VE SINIF SÜZGECİNDEN SONRA sayılıyor: "Hisse"
    // filtresindeyken tahvil tarafında kilitli 12 varlık olduğunu söylemek
    // kullanıcının o an baktığı listeyle ilgisiz bir sayı olurdu.
    if (sekme === "sell") return { varliklar: suzulmus, gizlenen: 0 };
    return {
      varliklar: suzulmus.filter((a) => a.can_buy),
      gizlenen: suzulmus.filter((a) => !a.can_buy).length,
    };
  }, [data, sekme, arama, sinif]);

  async function paraYatir() {
    if (!userId || yatiriliyor) return;
    setYatiriliyor(true);
    try {
      const sonuc = await depositCash(userId, 100000);
      setBildirim(`100.000 ₺ yatırıldı. Yeni bakiye: ${formatTRY(sonuc.cash_balance)}`);
      refetch();
    } catch (err: unknown) {
      setBildirim(err instanceof Error ? err.message : "Yatırma başarısız.");
    } finally {
      setYatiriliyor(false);
    }
  }

  function islemTamam() {
    setBildirim(
      `${secili?.name} için ${sekme === "buy" ? "alım" : "satış"} tamamlandı. ` +
        "Portföyünüz güncellendi.",
    );
    setSecili(null);
    refetch();
  }

  return (
    <div>
      <PageHeading
        kicker="İşlem"
        title="Al / Sat"
        description="Portföyünüze varlık ekleyin ya da çıkarın. Her işlem defterinize kaydedilir ve portföy ekranınıza anında yansır."
        actions={
          <Button variant="secondary" onClick={paraYatir} loading={yatiriliyor}>
            Para Yatır (100.000 ₺)
          </Button>
        }
      />

      {error && <ErrorBanner message={error} onDismiss={refetch} />}

      {bildirim && (
        <div className="mb-4 rounded-xl border border-brand-border bg-brand-tint px-4 py-3 text-[13.5px] font-medium text-brand dark:border-transparent">
          {bildirim}
        </div>
      )}

      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto]">
        <Card className="flex items-center justify-between p-5">
          <span className="text-xs font-semibold uppercase tracking-[.4px] text-ink-faint">
            Kullanılabilir nakit
          </span>
          <span className="font-display text-[24px] font-bold tracking-[-0.6px]">
            {data ? formatTRY(data.cash_balance) : "—"}
          </span>
        </Card>
        <Card className="flex items-center gap-2 p-2">
          {(["buy", "sell"] as const).map((s) => (
            <button
              key={s}
              onClick={() => {
                setSekme(s);
                setSecili(null);
              }}
              className={
                "min-h-11 flex-1 rounded-[10px] px-6 text-sm font-semibold transition-colors " +
                (s === sekme
                  ? "bg-brand text-white"
                  : "text-ink-muted hover:bg-black/[0.03] dark:hover:bg-white/[0.05]")
              }
            >
              {s === "buy" ? "Al" : "Sat"}
            </button>
          ))}
        </Card>
      </div>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.6fr_1fr]">
        <Card className="p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <input
              value={arama}
              onChange={(e) => setArama(e.target.value)}
              placeholder="Sembol ya da isim ara…"
              className="h-11 min-w-[200px] flex-1 rounded-[10px] border border-line px-4 text-sm outline-none transition-shadow focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] dark:border-transparent dark:bg-white/[0.06] dark:text-[#EDF1F7]"
            />
            <div className="flex flex-wrap gap-1.5">
              {SINIF_FILTRELERI.map((f) => (
                <button
                  key={f}
                  onClick={() => setSinif(f)}
                  className={
                    "min-h-10 rounded-lg px-[13px] py-[7px] text-xs font-semibold transition-colors " +
                    (f === sinif
                      ? "bg-brand text-white"
                      : "border border-line text-ink-muted dark:border-transparent dark:bg-white/5")
                  }
                >
                  {f === "Tümü" ? "Tümü" : SINIF_ETIKETLERI[f]}
                </button>
              ))}
            </div>
          </div>

          {loading && <p className="m-0 text-sm text-ink-faint">Varlıklar yükleniyor…</p>}

          {!loading && varliklar.length === 0 && (
            <p className="m-0 text-sm text-ink-faint">
              {sekme === "sell"
                ? "Satabileceğiniz bir pozisyonunuz yok."
                : data?.survey_score === null
                  ? "Risk anketiniz kayıtlı değil. Alım yapabilmek için önce anketi doldurmanız gerekiyor."
                  : gizlenen > 0
                    ? "Bu süzgece uyan ve risk puanınıza uygun varlık yok."
                    : "Aramanıza uyan varlık yok."}
            </p>
          )}

          <div className="flex flex-col">
            {/* Al sekmesinde liste zaten yalnızca alınabilirleri içeriyor,
                Sat sekmesinde kilit hiç uygulanmıyor (elindeki uyumsuz
                varlıktan çıkışın tek yolu satmaktır) — bu yüzden burada
                tıklanamaz satır YOK. */}
            {varliklar.map((a) => (
              <button
                key={a.symbol}
                onClick={() => setSecili(a)}
                className={
                  "flex items-center gap-3 border-t border-line2 py-3 text-left transition-colors first:border-t-0 hover:bg-black/[0.02] dark:border-transparent dark:hover:bg-white/[0.04]" +
                  (secili?.symbol === a.symbol ? " bg-brand-tint dark:bg-white/[0.06]" : "")
                }
              >
                <AssetLogo symbol={a.symbol} size={32} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{a.name}</div>
                  <div className="truncate text-xs text-ink-faint">
                    {a.symbol} · {SINIF_ETIKETLERI[a.asset_class] ?? a.asset_class}
                    {sekme === "sell" && ` · ${a.held_quantity} adet`}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  {/* GÖSTERİLEN RAKAM TL. Varlığın kendi fiyatı (ABD
                      hisselerinde USD) yalnızca ikinci satırda, birimiyle
                      birlikte yazılıyor — TL işaretiyle dolar rakamı
                      göstermek varlığı 40 kat ucuz gösteriyordu. */}
                  <div className="text-[13.5px] font-semibold">
                    {a.price_try === null ? "—" : formatTRY2(a.price_try)}
                  </div>
                  <div className="text-[11px] text-ink-faint">
                    {a.currency !== "TRY" && a.price !== null
                      ? `${formatNumberTR(a.price, 2)} ${a.currency} · `
                      : ""}
                    seviye {a.risk_level}
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Gizlenenlerin SAYISI söyleniyor: aradığı varlığı bulamayan
              kullanıcı, listenin neden kısa olduğunu bilmezse hatayı
              sistemde ya da kendinde arar. */}
          {!loading && sekme === "buy" && gizlenen > 0 && (
            <p className="m-0 mt-3 border-t border-line2 pt-3 text-[11.5px] text-ink-faint dark:border-transparent">
              Risk puanınıza ({data?.survey_score}/7) uymayan ya da fiyatı alınamayan {gizlenen}{" "}
              varlık listelenmiyor.
            </p>
          )}
        </Card>

        <Card className="p-6">
          {secili && userId ? (
            <TradePanel
              userId={userId}
              asset={secili}
              side={sekme}
              onDone={islemTamam}
              onClose={() => setSecili(null)}
            />
          ) : (
            <p className="m-0 text-sm text-ink-faint">
              {sekme === "buy"
                ? "Almak istediğiniz varlığı listeden seçin."
                : "Satmak istediğiniz pozisyonu listeden seçin."}
            </p>
          )}
        </Card>
      </div>

      <p className="m-0 mt-5 text-center text-xs italic text-ink-soft dark:text-ink-faint">
        {INVESTMENT_DISCLAIMER}
      </p>
    </div>
  );
}
