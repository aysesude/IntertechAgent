"""BloombergHT sağlayıcısı: CANLI genel piyasa gündemi (son dakika başlıkları).

`kap_p.py` ile aynı sınıfta bir kaynak: kullanıcı sorusu ANINDA çağrılır,
veritabanına yazılmaz, RAG/Chroma'ya girmez. İkisi arasındaki iş bölümü:
KAP ŞİRKETE ÖZEL bildirimleri, bu sağlayıcı GENEL piyasa gündemini verir
("bugün piyasada ne oldu", "son piyasa haberleri neler") — bu soruların
başka hiçbir kaynağı yoktu; RAG yalnızca değişmeyecek arşiv belgesi tutuyor.

NEDEN ŞİRKET BAZLI HABER YOK (ölçümle karar verildi, 2026-08-24):
BloombergHT'de bir hissenin kendi sayfasındaki ("/borsa/hisse/asels-aselsan-detay")
"İlgili Haberler" bloğu, genel "/borsa" sayfasındakiyle BİREBİR AYNI çıktı —
yani şirkete özel değil, sitenin son haberleri. Şirket bazlı haber ancak site
içi aramadan gelir, `robots.txt` ise `/arama`, `/etiket` ve `/imkb-haberleri/*`
yollarını açıkça yasaklıyor. Bu yüzden şirket bazlı ihtiyaç KAP'ta bırakıldı.

NEDEN SITEMAP KULLANILMIYOR:
`sitemap_google_news.xml` makine için yayınlanmış ve ayrıştırması temiz olurdu,
ama içeriği ölçüldüğünde iki ay eskiydi (tüm kayıtlar 23–25 Haziran 2026, site
ise canlı). Donmuş bir kaynağı "canlı gündem" diye sunmak, güncel bilgi
vaadinin sessizce yalan olması demekti.

VERİDEN NE ALINIR, NE ALINMAZ:
`/sondakika` her maddede saat + tarih + başlık taşıyor; madde başına AYRI
BAĞLANTI YOK (tüm paylaşım bağlantıları sayfanın tamamına gidiyor). Bu yüzden
madde başına link üretilmez, kaynak olarak sayfanın kendisi verilir — olmayan
bir permalink uydurmaktansa eksik bilgiyle kalınır (CLAUDE.md "Uydurmama").
Başlık, sitenin kendi ifadesiyle aynen taşınır; haber metni alınmaz.

AYRIŞTIRMA SINIFLARA BAĞLI DEĞİL: sayfa Tailwind sınıfları kullanıyor
("font-unna font-bold text-xl") ve bunlar bir tema güncellemesinde sessizce
değişir. Bunun yerine figcaption'ın doğrudan çocukları biçimlerine göre
ayrılıyor: saate benzeyen saat, tarihe benzeyen tarih, geri kalanın en uzunu
başlık. Site yapısını tamamen değiştirirse sonuç boş liste olur ve çağıran
taraf "gündem alınamadı" der — yanlış veri döndürmez.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from lxml import html as lxml_html

from app.providers.base import ProviderError

logger = logging.getLogger(__name__)

_SONDAKIKA_URL = "https://www.bloomberght.com/sondakika"

# Varsayılan httpx User-Agent'ı ile bazı CDN'ler bot koruması devreye sokuyor.
# Tarayıcı taklidi değil, kimliğini gizlemeyen sade bir istek: robots.txt'nin
# izin verdiği bir yolu, sayfa başına tek istekle ve önbellekle çekiyoruz.
_ISTEK_BASLIKLARI = {
    "User-Agent": "Mozilla/5.0 (compatible; FinansDanismaniBot/1.0)",
    "Accept-Language": "tr-TR,tr;q=0.9",
}

_ZAMAN_ASIMI = 15.0

# Son dakika akışı dakikalar mertebesinde değişiyor; 5 dakikalık önbellek
# demo sırasında arka arkaya sorulan sorularda siteye tekrar gitmeyi önler.
_ONBELLEK_SANIYE = 300.0

_AYLAR = {
    "ocak": 1,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "eylül": 9,
    "ekim": 10,
    "kasım": 11,
    "aralık": 12,
}

# "24 Ağustos 2026, Pazartesi" — gün adı yok sayılır.
_TARIH_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})\b")
# Tek başına saat taşıyan kutuyu ("14:38") başlık adaylarından elemek için.
_SADECE_SAAT_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class PiyasaBasligi:
    baslik: str
    tarih: datetime | None
    kaynak_url: str


def _metin(element: Any) -> str:
    """Bir düğümün görünen metni, boşluklar tek boşluğa indirilmiş hâlde."""
    return re.sub(r"\s+", " ", element.text_content()).strip()


def _tarih_ayristir(figcaption_metni: str) -> datetime | None:
    """ "14:38 ... 24 Ağustos 2026, Pazartesi" -> datetime(2026, 8, 24, 14, 38).

    Saat bulunamazsa gün 00:00 kabul edilir; tarih bulunamazsa None döner —
    tarihsiz bir başlık listeden düşürülmez, yalnızca tarihi gösterilmez.
    """
    tarih_eslesme = _TARIH_RE.search(figcaption_metni)
    if not tarih_eslesme:
        return None

    ay = _AYLAR.get(tarih_eslesme.group(2).lower())
    if ay is None:
        logger.warning("bloomberg_ht_p: tanınmayan ay adı: %r", tarih_eslesme.group(2))
        return None

    saat_eslesme = re.search(r"\b(\d{1,2}):(\d{2})\b", figcaption_metni)
    saat = int(saat_eslesme.group(1)) if saat_eslesme else 0
    dakika = int(saat_eslesme.group(2)) if saat_eslesme else 0

    try:
        return datetime(int(tarih_eslesme.group(3)), ay, int(tarih_eslesme.group(1)), saat, dakika)
    except ValueError:
        logger.warning("bloomberg_ht_p: geçersiz tarih: %r", figcaption_metni[:80])
        return None


def _baslik_sec(figcaption: Any) -> str | None:
    """figcaption'ın doğrudan çocuklarından saat ve tarih kutularını eleyip
    geriye kalanların EN UZUNUNU başlık sayar.

    Sınıf adına bakılmamasının nedeni modül başlığında; "en uzun" seçilmesinin
    nedeni ise başlığın her zaman etiketlerden ("PİYASALAR", kategori rozeti)
    uzun olması ve rozetlerin sayfadan sayfaya değişmesi.
    """
    adaylar = []
    for cocuk in figcaption:
        metin = _metin(cocuk)
        if not metin or _SADECE_SAAT_RE.fullmatch(metin):
            continue
        # Tarih kutusu ("24 Ağustos 2026, Pazartesi") tarihle BAŞLAR ve kısadır.
        # Gerçek bir başlık tarihle başlasa bile 40 karakterden uzun olur, bu
        # yüzden eşik ikisini ayırmaya yetiyor — sadece `fullmatch` yeterli
        # olmazdı, gün adı ("Pazartesi") tarih kalıbının dışında kalıyor.
        if _TARIH_RE.match(metin) and len(metin) <= 40:
            continue
        adaylar.append(metin)

    if not adaylar:
        return None
    return max(adaylar, key=len)


def basliklari_ayristir(
    html_metni: str, *, kaynak_url: str = _SONDAKIKA_URL
) -> list[PiyasaBasligi]:
    """Ham HTML'den başlık listesi. Ağdan bağımsız — gerçek kesitle test edilir.

    Ayrıştırılamayan tek bir madde tüm listeyi düşürmez: o madde atlanır ve
    loglanır. Demo sırasında sitenin bir maddesi bozuk geldi diye gündemin
    tamamının kaybolması, eksik bir maddeden daha kötü.
    """
    try:
        agac = lxml_html.fromstring(html_metni)
    except Exception as exc:  # lxml çeşitli parse hataları atabiliyor
        logger.warning("bloomberg_ht_p: HTML ayrıştırılamadı: %s", exc)
        return []

    basliklar: list[PiyasaBasligi] = []
    for figcaption in agac.iter("figcaption"):
        baslik = _baslik_sec(figcaption)
        if not baslik:
            continue
        basliklar.append(
            PiyasaBasligi(
                baslik=baslik,
                tarih=_tarih_ayristir(_metin(figcaption)),
                kaynak_url=kaynak_url,
            )
        )
    return basliklar


class _Onbellek:
    """Süreç içi, süreli önbellek. Konteyner yeniden başlayınca boşalır —
    kalıcılık gerekmiyor, amaç arka arkaya gelen sorularda aynı sayfayı
    tekrar tekrar çekmemek."""

    def __init__(self, omur_saniye: float) -> None:
        self._omur = omur_saniye
        self._kilit = threading.Lock()
        self._deger: list[PiyasaBasligi] | None = None
        self._zaman = 0.0

    def oku(self) -> list[PiyasaBasligi] | None:
        with self._kilit:
            if self._deger is None or (time.monotonic() - self._zaman) > self._omur:
                return None
            return self._deger

    def yaz(self, deger: list[PiyasaBasligi]) -> None:
        with self._kilit:
            self._deger = deger
            self._zaman = time.monotonic()


_onbellek = _Onbellek(_ONBELLEK_SANIYE)


class BloombergHtProvider:
    """Son dakika akışını çeker. `pykap` gibi üçüncü taraf bir sarmalayıcı
    yok; sayfa sunucu tarafında render edildiği için (JS gerekmiyor, ölçüldü)
    httpx + lxml yetiyor ve yeni bir bağımlılık gelmiyor."""

    def fetch_latest_headlines(self, limit: int = 8) -> list[PiyasaBasligi]:
        onbellekten = _onbellek.oku()
        if onbellekten is not None:
            return onbellekten[:limit]

        try:
            yanit = httpx.get(
                _SONDAKIKA_URL,
                headers=_ISTEK_BASLIKLARI,
                timeout=_ZAMAN_ASIMI,
                follow_redirects=True,
            )
            yanit.raise_for_status()
        except Exception as exc:
            raise ProviderError("bloomberght", "sondakika", f"istek başarısız: {exc}") from exc

        basliklar = basliklari_ayristir(yanit.text)
        if not basliklar:
            # Sayfa geldi ama hiçbir madde ayrıştırılamadı: büyük ihtimalle
            # site yapısı değişti. Boş liste döndürüp sessizce "haber yok"
            # demek yanıltıcı olurdu — bu bir ARIZA, öyle raporlanır.
            raise ProviderError(
                "bloomberght", "sondakika", "sayfa alındı ama hiçbir başlık ayrıştırılamadı"
            )

        # En yeni en üstte. Site zaten böyle sıralıyor (ölçüldü) ama garanti
        # değil; tarihsiz maddeler sona atılır, listeden düşürülmez.
        basliklar.sort(key=lambda b: b.tarih or datetime.min, reverse=True)
        _onbellek.yaz(basliklar)
        return basliklar[:limit]
