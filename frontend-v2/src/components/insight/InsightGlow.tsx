/**
 * Ekran kenarlarında yavaşça dalgalanan mavi ışık.
 *
 * NE İŞE YARIYOR: özet üretimi beş tool çağrısı + bir LLM turu, birkaç saniye
 * sürüyor. Işık bu süreyi GİZLEMİYOR, tersine görünür kılıyor — "sistem
 * çalışıyor" sinyali, boş bir bekleme ekranından hem dürüst hem de daha
 * katlanılır.
 *
 * NEDEN CANVAS DEĞİL: dört kenara yerleşmiş, bulanıklaştırılmış gradyanlar
 * CSS ile yeterli. Canvas bir çizim döngüsü, bir yeniden boyutlandırma
 * dinleyicisi ve tema değişiminde yeniden çizim gerektirirdi; görsel kazanç
 * bunu karşılamıyor.
 *
 * HAREKETİ AZALT: işletim sisteminde bu ayar açıksa dalga durur, sabit bir
 * ışıma kalır (piyasa şeridinde koyduğumuz standardın aynısı, bkz.
 * `index.css`). Işığı tamamen kaldırmıyoruz — o zaman "çalışıyor" sinyali de
 * kaybolurdu.
 */
export function InsightGlow({ active }: { active: boolean }) {
  if (!active) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-[190]" aria-hidden>
      <span className="insight-glow insight-glow-top" />
      <span className="insight-glow insight-glow-bottom" />
      <span className="insight-glow insight-glow-left" />
      <span className="insight-glow insight-glow-right" />
    </div>
  );
}
