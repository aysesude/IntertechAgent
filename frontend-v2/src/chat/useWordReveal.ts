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
 * Geride kalındığında hızlanır: her turda kalan işin onda biri açılır, yani
 * akış bittiğinde ekran birkaç yüz milisaniyede yetişir ama normal akışta
 * turda bir-iki kelimeyle yumuşak kalır. Sabit hız olsaydı uzun bir yanıtın
 * sonu, sunucu çoktan bitirmişken hâlâ yazılıyor olurdu.
 */

const TUR_SURESI_MS = 45;
// Her turda kalanın 1/10'u açılır. Küçük değer = daha çabuk yetişme.
const YETISME_BOLENI = 10;

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

export function useWordReveal(metin: string, aktif: boolean): string {
  const sonlar = useMemo(() => kelimeSonlari(metin), [metin]);
  const toplam = sonlar.length;
  const [acilan, setAcilan] = useState(toplam);
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
        return mevcut + Math.max(1, Math.ceil(kalan / YETISME_BOLENI));
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
