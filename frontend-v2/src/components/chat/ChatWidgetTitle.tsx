/**
 * Sohbet panelinin başlığı — SABİT metin.
 *
 * Önceden "Vira Chat" olarak açılıp ~1 sn sonra harf harf "Ai Chat"e
 * dönüşüyordu (framer-motion `layout` + `AnimatePresence`). Animasyon
 * KALDIRILDI (kullanıcı kararı, 2 Eylül 2026): panel her açılışta yeniden
 * mount olduğu için dönüşüm her seferinde baştan oynuyordu ve bir kez
 * görüldükten sonra bilgi taşımayan, yalnızca gözü çeken bir hareket
 * hâline geliyordu.
 *
 * Bileşen olarak duruyor (satır içine gömülmedi) çünkü başlık metni tek bir
 * yerde kalsın; ileride ürün adı değişirse tek dosya değişir.
 */
export function ChatWidgetTitle() {
  return <div className="flex h-[18px] items-center text-sm font-semibold">Ai Chat</div>;
}
