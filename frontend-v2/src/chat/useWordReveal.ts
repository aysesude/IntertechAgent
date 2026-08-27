import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Akan metni KELİME KELİME açar.
 *
 * NEDEN: SSE token'ları ağın getirdiği ritimde geliyor — bazen tek harf,
 * bazen yarım cümle, arada uzun boşluklar. Doğrudan basıldığında metin
 * kekeleyerek beliriyordu. Bu kancа ekranı ağdan AYIRIYOR: gelen metin bir
 * hedef, gösterilen metin ona sabit tempoda yetişiyor.
 *
 * Kelime sınırı bilerek: harf harf açmak bir finans metnini okunmaz yapıyor
 * (sayılar ve para birimleri parça parça beliriyor), cümle cümle açmak ise
 * akışı hissettirmiyor.
 *
 * Geride kalındığında hızlanır ama SIÇRAMADAN: her turda kalan işin bir
 * kesri açılır, üstten de tavanla sınırlanır. Sabit hız olsaydı uzun bir
 * yanıtın sonu, sunucu çoktan bitirmişken hâlâ yazılıyor olurdu.
 *
 * TEMPO (27 Ağustos 2026'da yeniden ayarlandı). Önceki değerler 45 ms'de
 * kalanın 1/10'uydu ve TAVAN YOKTU: tamamlanmış 100 kelimelik bir yanıtın
 * ilk turunda ekrana tek seferde 10 kelime düşüyordu. Metin kelime kelime
 * değil, öbek öbek "patlıyordu" — asıl pürüz buydu, hız değil.
 *
 * Şimdi tur 24 ms, adım en fazla 3 kelime. Aynı 100 kelimelik yanıtta:
 *
 *              eski (45ms, /10)      yeni (24ms, /26, tavan 3)
 *   ilk adım   10 kelime             3 kelime
 *   güncelleme 28 kare               ~56 kare
 *   süre       ~1,26 sn              ~1,34 sn
 *
 * Yani süre neredeyse aynı, kare sayısı iki katı, sıçrama üçte bir. Canlı
 * akışta zaten turda 1 kelime düşüyor (kelimeler ağdan tek tek geliyor),
 * orada değişen tek şey temponun 45 ms'den 24 ms'ye inmesi.
 */

const TUR_SURESI_MS = 24;
// Her turda kalanın 1/26'sı açılır. Küçük değer = daha çabuk yetişme.
const YETISME_BOLENI = 26;
// Bir turda açılabilecek EN FAZLA kelime. Asıl yumuşaklık ayarı burada:
// tavansız bırakılırsa uzun bir yanıtın başında ekrana öbek düşer.
const MAKS_ADIM = 3;

/** Kelime sonlarının indeksleri. Boşluklar korunur, metin birebir yeniden kurulur. */
function kelimeSonlari(metin: string): number[] {
  const sonlar: number[] = [];
  const desen = /\S+/g;
  let eslesme: RegExpExecArray | null;
  while ((eslesme = desen.exec(metin)) !== null) {
    sonlar.push(eslesme.index + eslesme[0].length);
  }
  return sonlar;
}

export interface KelimeAcmaSecenekleri {
  /**
   * Metin ilk render'da TAM gelmiş olsa bile baştan açılsın mı?
   *
   * Varsayılan `false` ve bu bilinçli: sohbet geçmişi yeniden çizildiğinde
   * (tema değişimi, sayfa dönüşü) tamamlanmış mesajlar yeniden yazılmaya
   * başlamamalı — okunmuş bir metnin gözünüzün önünde silinip yeniden
   * yazılması hata gibi görünür.
   *
   * `true` yalnızca metnin İLK KEZ göründüğü, akıştan gelmeyen yerler için:
   * sayfa açılışındaki karşılama mesajı gibi.
   */
  bastanBasla?: boolean;
}

export function useWordReveal(
  metin: string,
  aktif: boolean,
  { bastanBasla = false }: KelimeAcmaSecenekleri = {},
): string {
  const sonlar = useMemo(() => kelimeSonlari(metin), [metin]);
  const toplam = sonlar.length;
  const [acilan, setAcilan] = useState(bastanBasla ? 0 : toplam);
  const oncekiMetin = useRef(metin);

  // Hareket azaltma tercihi: animasyon bir tercih, içerik değil — kapalıysa
  // metin olduğu gibi görünür.
  const azaltilmisHareket = useMemo(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true,
    [],
  );

  useEffect(() => {
    const onceki = oncekiMetin.current;
    oncekiMetin.current = metin;
    // Metin uzamak yerine DEĞİŞTİYSE (yeni mesaj, hata sonrası yeniden
    // yazım) sayaç sıfırlanır; aksi halde yeni metnin ortasından başlardı.
    if (!metin.startsWith(onceki)) {
      setAcilan(0);
    }
  }, [metin]);

  useEffect(() => {
    if (azaltilmisHareket) {
      setAcilan(toplam);
      return;
    }
    if (acilan >= toplam) return;

    const zamanlayici = window.setInterval(() => {
      setAcilan((mevcut) => {
        if (mevcut >= toplam) return mevcut;
        const kalan = toplam - mevcut;
        const adim = Math.min(MAKS_ADIM, Math.max(1, Math.ceil(kalan / YETISME_BOLENI)));
        return mevcut + adim;
      });
    }, TUR_SURESI_MS);

    return () => window.clearInterval(zamanlayici);
  }, [acilan, toplam, azaltilmisHareket]);

  // Akış bittiyse ve sayaç yetiştiyse metnin KENDİSİ döner (yeni bir string
  // üretilmez) — markdown ağacı gereksiz yere yeniden kurulmaz.
  if (azaltilmisHareket || (!aktif && acilan >= toplam)) return metin;
  if (acilan >= toplam) return metin;
  if (acilan <= 0) return "";
  return metin.slice(0, sonlar[acilan - 1]);
}
