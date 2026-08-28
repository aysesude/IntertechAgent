import { useEffect, useState } from "react";
import { AssetLogo } from "@/components/common/AssetLogo";
import { Button } from "@/components/common/Button";
import {
  executeTrade,
  previewTrade,
  type ApiTradableAsset,
  type ApiTradePreview,
  type ApiTradeSide,
} from "@/api/trade";
import { formatNumberTR, formatTRY, formatTRY2 } from "@/utils/format";

/**
 * Seçilen varlık için emir paneli.
 *
 * ÖN İZLEME SUNUCUDAN GELİR, istemcide hesaplanmaz. Miktar sınıf
 * hassasiyetine yuvarlanıyor, kur uygulanıyor ve bakiye kontrol ediliyor —
 * bunları burada tekrar yazmak, iki ayrı hesabın ayrışması demek olurdu.
 * Kullanıcı onayladığı rakamı sunucudan görüyor.
 */

interface TradePanelProps {
  userId: string;
  asset: ApiTradableAsset;
  side: ApiTradeSide;
  onDone: () => void;
  onClose: () => void;
}

function tarihTR(iso: string): string {
  const [y, a, g] = iso.split("-");
  return `${g}.${a}.${y}`;
}

export function TradePanel({ userId, asset, side, onDone, onClose }: TradePanelProps) {
  const [miktar, setMiktar] = useState("");
  const [onizleme, setOnizleme] = useState<ApiTradePreview | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [bekliyor, setBekliyor] = useState(false);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  const sayi = Number(miktar.replace(",", "."));
  const gecerli = Number.isFinite(sayi) && sayi > 0;

  // Miktar değişince ön izleme yeniden alınır. Gecikme (debounce) var:
  // her tuş vuruşunda sunucuya gitmek canlı fiyat çekimini de tetiklerdi.
  useEffect(() => {
    if (!gecerli) {
      setOnizleme(null);
      setHata(null);
      return;
    }
    let iptal = false;
    const zamanlayici = window.setTimeout(() => {
      setBekliyor(true);
      previewTrade(userId, asset.symbol, side, sayi)
        .then((sonuc) => {
          if (!iptal) {
            setOnizleme(sonuc);
            setHata(null);
          }
        })
        .catch((err: unknown) => {
          if (!iptal) {
            setOnizleme(null);
            setHata(err instanceof Error ? err.message : "Hesaplanamadı.");
          }
        })
        .finally(() => {
          if (!iptal) setBekliyor(false);
        });
    }, 350);

    return () => {
      iptal = true;
      window.clearTimeout(zamanlayici);
    };
  }, [userId, asset.symbol, side, sayi, gecerli]);

  async function onayla() {
    if (!onizleme || gonderiliyor) return;
    setGonderiliyor(true);
    setHata(null);
    try {
      await executeTrade(userId, asset.symbol, side, sayi);
      onDone();
    } catch (err: unknown) {
      setHata(err instanceof Error ? err.message : "İşlem tamamlanamadı.");
    } finally {
      setGonderiliyor(false);
    }
  }

  const alim = side === "buy";
  // Yuvarlama kullanıcının yazdığını değiştirdiyse SÖYLENMELİ; sessizce
  // 3,7 yerine 3 adet almak "istediğim bu değildi" anıdır.
  const yuvarlandi = onizleme !== null && onizleme.quantity !== sayi;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <AssetLogo symbol={asset.symbol} size={40} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{asset.name}</div>
          <div className="text-xs text-ink-faint">
            {asset.symbol}
            {asset.held_quantity > 0 && ` · elinizde ${asset.held_quantity}`}
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg px-2 py-1 text-xs font-semibold text-ink-muted hover:text-ink"
        >
          Kapat
        </button>
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-[.4px] text-ink-faint">
          {alim ? "Alınacak miktar" : "Satılacak miktar"}
        </span>
        <input
          value={miktar}
          onChange={(e) => setMiktar(e.target.value)}
          inputMode="decimal"
          placeholder={asset.quantity_step === 1 ? "örn. 10" : "örn. 2,5"}
          autoFocus
          className="h-[46px] rounded-[10px] border border-line px-4 text-sm outline-none transition-shadow focus:border-brand focus:shadow-[0_0_0_3px_rgba(37,87,232,.1)] dark:border-transparent dark:bg-white/[0.06] dark:text-[#EDF1F7]"
        />
        <span className="text-[11.5px] text-ink-faint">
          {asset.quantity_step === 1
            ? "Tam sayı girilir."
            : `En küçük adım ${String(asset.quantity_step).replace(".", ",")}.`}
        </span>
      </label>

      {bekliyor && <p className="m-0 text-xs text-ink-faint">Hesaplanıyor…</p>}

      {hata && (
        <p className="m-0 rounded-lg bg-danger-tint px-3 py-2 text-[13px] font-medium text-danger">
          {hata}
        </p>
      )}

      {onizleme && (
        <div className="flex flex-col gap-2 rounded-xl border border-line p-4 text-[13px] dark:border-transparent dark:bg-white/[0.04]">
          {yuvarlandi && (
            <p className="m-0 text-[12px] font-medium text-ink-soft">
              Miktar {String(onizleme.quantity).replace(".", ",")} olarak yuvarlandı.
            </p>
          )}
          {/* Birim fiyat TL olarak yazılır; TRY dışı varlıkta kendi para
              biriminden rakam parantez içinde ikinci bilgi olarak durur.
              Kuruş gösteriliyor: fon birim fiyatları 0,11 TL mertebesinde
              ve tam sayıya yuvarlanınca "₺0" görünüyordu. */}
          <Satir
            etiket="Birim fiyat"
            deger={`${formatTRY2(onizleme.price * onizleme.fx_rate_to_try)}${
              onizleme.currency !== "TRY"
                ? ` (${formatNumberTR(onizleme.price, 2)} ${onizleme.currency})`
                : ""
            }`}
          />
          <Satir etiket="Tutar" deger={formatTRY(onizleme.gross_try)} />
          <Satir etiket="Mevcut bakiye" deger={formatTRY(onizleme.cash_before)} />
          <Satir
            etiket="İşlem sonrası bakiye"
            deger={formatTRY(onizleme.cash_after)}
            vurgulu
          />
          {/* Fiyatın hangi ana ait olduğu SÖYLENİR. Canlı değilse kullanıcı
              dünkü kapanıştan işlem yaptığını bilmeli. */}
          <p className="m-0 mt-1 text-[11.5px] text-ink-faint">
            {onizleme.price_is_live
              ? "Fiyat şu anda borsadan alındı."
              : `Fiyat ${tarihTR(onizleme.price_date)} kapanışına ait — canlı fiyat alınamadı.`}
            {onizleme.price_stale && " Bu fiyat beklenenden eski."}
          </p>
        </div>
      )}

      <Button onClick={onayla} disabled={!onizleme || bekliyor} loading={gonderiliyor}>
        {alim ? "Alımı onayla" : "Satışı onayla"}
      </Button>
    </div>
  );
}

function Satir({
  etiket,
  deger,
  vurgulu = false,
}: {
  etiket: string;
  deger: string;
  vurgulu?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-ink-faint">{etiket}</span>
      <span className={vurgulu ? "font-display text-[15px] font-bold" : "font-semibold"}>
        {deger}
      </span>
    </div>
  );
}
