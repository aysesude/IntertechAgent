import { useState } from "react";
import { getApiBaseUrl } from "@/api/client";

/**
 * Varlığın yuvarlak logosu; yoksa harf rozeti.
 *
 * YUVARLAK KIRPMA GÜVENLİ. Ölçüldü (27 Ağustos 2026, 14 sembol): logostream
 * logolarının tamamı `60x60` kare ve zemini tam dolu. Daire içine kırpmak
 * yalnızca köşeleri alıyor, tıpkı uygulama ikonlarında olduğu gibi. Geniş
 * bir kelime-logo (wordmark) gelseydi kırpma metni keserdi ve o zaman
 * "daire içine sığdır + kenar boşluğu" gerekirdi.
 *
 * Sağlayıcının kendi dairesel varyantı YOK: `variant`, `shape`, `radius`
 * gibi parametrelerin hiçbiri çıktıyı değiştirmiyor (denendi), `format=png`
 * ise sessizce yer tutucuya düşüyor. Yuvarlağı biz yapıyoruz.
 *
 * `<img>` bilerek: logo üçüncü taraf SVG'si ve `dangerouslySetInnerHTML` ile
 * DOM'a gömmek script çalıştırma imkânı verirdi. `<img>` içindeki SVG
 * tarayıcı tarafından yalıtılıyor.
 */

interface AssetLogoProps {
  symbol: string;
  /** Kenar uzunluğu (px). Tablo satırında 28, listede 36 civarı. */
  size?: number;
  className?: string;
}

/**
 * Rozet zemini sembolden türetilir: aynı varlık her yerde AYNI rengi alır.
 *
 * Rastgele ya da sıraya bağlı renk seçilseydi aynı hisse portföy tablosunda
 * mavi, Al/Sat listesinde yeşil görünür ve göz onu iki ayrı şey sanardı.
 * Marka paletinden bağımsız, doygunluğu düşük tonlar — rozet logonun yerine
 * geçiyor, dikkat çekmesi gerekmiyor.
 */
const ROZET_RENKLERI = [
  "#5B7DB1",
  "#6E8B6E",
  "#A8794F",
  "#8A6EA8",
  "#B1705B",
  "#4F8A8B",
] as const;

function rozetRengi(symbol: string): string {
  let toplam = 0;
  for (let i = 0; i < symbol.length; i++) toplam = (toplam * 31 + symbol.charCodeAt(i)) >>> 0;
  return ROZET_RENKLERI[toplam % ROZET_RENKLERI.length];
}

/** Rozette görünen harfler: sembolün ilk ikisi. */
function rozetHarfleri(symbol: string): string {
  return symbol.slice(0, 2).toUpperCase();
}

export function AssetLogo({ symbol, size = 28, className = "" }: AssetLogoProps) {
  // Logo yoksa uç 404 döner; `onError` rozete düşürür. Denemeyi hiç
  // yapmamak yerine denemek doğru: hangi sembolde logo olduğunu istemci
  // bilmiyor ve bilmesi de gerekmiyor.
  const [logoYok, setLogoYok] = useState(false);

  const ortak = "shrink-0 rounded-full object-cover";
  const stil = { width: size, height: size };

  if (logoYok) {
    return (
      <span
        aria-hidden="true"
        className={`${ortak} grid place-items-center font-semibold text-white ${className}`}
        style={{
          ...stil,
          background: rozetRengi(symbol),
          fontSize: Math.round(size * 0.38),
        }}
      >
        {rozetHarfleri(symbol)}
      </span>
    );
  }

  return (
    <img
      src={`${getApiBaseUrl()}/api/logos/${encodeURIComponent(symbol)}`}
      // Sembol zaten yanında yazılı; ekran okuyucuya iki kez okutmanın
      // faydası yok.
      alt=""
      aria-hidden="true"
      loading="lazy"
      width={size}
      height={size}
      style={stil}
      className={`${ortak} bg-line2 ${className}`}
      onError={() => setLogoYok(true)}
    />
  );
}
