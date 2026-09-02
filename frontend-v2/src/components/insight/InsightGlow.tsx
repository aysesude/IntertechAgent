import { motion } from "framer-motion";

/**
 * Ekran kenarlarında yavaşça dalgalanan mavi ışık.
 *
 * NE İŞE YARIYOR: özet üretimi beş tool çağrısı + bir LLM turu, birkaç saniye
 * sürüyor. Işık bu süreyi GİZLEMİYOR, tersine görünür kılıyor — "sistem
 * çalışıyor" sinyali, boş bir bekleme ekranından hem dürüst hem de daha
 * katlanılır.
 *
 * BELİRMESİ YUMUŞAK. Önce tam parlaklıkta, bir anda ortaya çıkıyordu ve
 * düğmeye basar basmaz ekran "çakıyordu" (sahada ölçüldü, 2 Eylül 2026).
 * Artık ~700 ms'de açılıp ~400 ms'de kapanıyor; çağıran taraf
 * `AnimatePresence` ile sarmalı ki sönme de oynayabilsin.
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
export function InsightGlow() {
  return (
    <motion.div
      className="pointer-events-none fixed inset-0 z-[190]"
      aria-hidden
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ opacity: { duration: 0.7, ease: "easeOut" } }}
    >
      <span className="insight-glow insight-glow-top" />
      <span className="insight-glow insight-glow-bottom" />
      <span className="insight-glow insight-glow-left" />
      <span className="insight-glow insight-glow-right" />
    </motion.div>
  );
}
