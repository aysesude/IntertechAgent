import type { MarketIndicator } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { formatPct } from "@/utils/format";
import { POSITIVE, NEGATIVE, INK_FAINT } from "@/utils/colors";

/**
 * Piyasa nabzı: yatay KAYAN şerit.
 *
 * Eskiden sabit bir ızgaraydı ve beş kutuya sığan kadar gösterge
 * alabiliyordu; şerit kaydığı için gösterge sayısı artık yerleşimi
 * belirlemiyor.
 *
 * NASIL KAYIYOR: liste iki kez basılıyor ve şerit -%50 kadar ötelendiğinde
 * ilk kopyanın sonu ikincinin başıyla çakışıyor, yani sıfıra dönüş
 * görünmüyor. İkinci kopya `aria-hidden`: ekran okuyucu aynı göstergeleri
 * iki kez okumamalı.
 *
 * DURMA: fareyle üstüne gelince ve içindeki bir öğe klavye odağı alınca
 * animasyon duruyor — durmayan bir şeritte rakam okunamaz.
 *
 * HAREKETİ AZALT: işletim sisteminde bu ayar açıksa şerit hiç kaymıyor,
 * elle kaydırılan bir listeye düşüyor (`index.css`).
 *
 * AZ GÖSTERGEDE KAYMAZ: şerit ekrandan dar kaldığında kayma, aradaki boşluğu
 * gezdirmekten ibaret olurdu. Veri kısmen geldiğinde (tek gösterge) olan tam
 * da budur.
 */

/** Altında kayma yerine sabit yerleşim kullanılır. */
const KAYMA_ESIGI = 5;

interface MarketTickerProps {
  indicators: MarketIndicator[];
}

export function MarketTicker({ indicators }: MarketTickerProps) {
  if (indicators.length === 0) {
    // Boş bir kart "yükleniyor" ile "veri yok"u aynı gösterir.
    return (
      <Card className="mb-6 px-[22px] py-[18px]">
        <p className="m-0 text-[13px] text-ink-faint">Gösterge verisi alınamadı.</p>
      </Card>
    );
  }

  const kayacak = indicators.length >= KAYMA_ESIGI;

  if (!kayacak) {
    return (
      <Card className="mb-6 grid grid-cols-2 gap-3 px-[22px] py-[18px] sm:grid-cols-3 lg:grid-cols-5">
        {indicators.map((ind) => (
          <Gosterge key={ind.id} indicator={ind} />
        ))}
      </Card>
    );
  }

  return (
    <Card className="ticker-viewport mb-6 overflow-hidden px-0 py-[18px]">
      <div className="ticker-track flex w-max animate-tickerScroll gap-10 pl-[22px] hover:[animation-play-state:paused] focus-within:[animation-play-state:paused]">
        {indicators.map((ind) => (
          <Gosterge key={ind.id} indicator={ind} />
        ))}
        {indicators.map((ind) => (
          <Gosterge key={`kopya-${ind.id}`} indicator={ind} aria-hidden />
        ))}
      </div>
    </Card>
  );
}

function Gosterge({ indicator, ...rest }: { indicator: MarketIndicator; "aria-hidden"?: boolean }) {
  // `null` = değişim HESAPLANAMADI (seride tek nokta var). Sıfırdan
  // ayrı tutuluyor: "değişmedi" ile "bilmiyoruz" aynı şey değil.
  const degisim = indicator.changePct;
  const renk =
    degisim === null ? INK_FAINT : degisim > 0 ? POSITIVE : degisim < 0 ? NEGATIVE : INK_FAINT;

  return (
    <div className="min-w-[120px] shrink-0" {...rest}>
      <div className="text-[11.5px] font-semibold tracking-[.5px] text-ink-faint">
        {indicator.label}
      </div>
      <div className="mt-[5px] flex items-baseline gap-2">
        <span className="whitespace-nowrap font-display text-[19px] font-bold">
          {indicator.value}
        </span>
        <span className="text-[13px] font-semibold" style={{ color: renk }}>
          {degisim === null ? "—" : degisim === 0 ? "0,00" : formatPct(degisim)}
        </span>
      </div>
      {/* Fiyatın günü HER ZAMAN yazılır: piyasa hafta sonu kapalı,
          tarihsiz bir fiyat olmayan bir tazelik iddiasıdır (AK 5.3). */}
      <div className="mt-[3px] whitespace-nowrap text-[10.5px] text-ink-faint">
        {indicator.priceDate}
        {indicator.stale ? " · eski" : ""}
      </div>
    </div>
  );
}
