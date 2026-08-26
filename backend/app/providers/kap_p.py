"""KAP (Kamuyu Aydınlatma Platformu) sağlayıcısı: CANLI bildirim sorgusu.

Diğer sağlayıcılardan (yfinance_p, tcmb) farkı: onlar veriyi bir kez
`backfill`/`daily_update` ile veritabanına yazıp saklar; bu sağlayıcı Piyasa
Ajanı'nın kullanıcı sorgusu ANINDA çağırdığı canlı bir kaynaktır — sonuç
veritabanına yazılmaz, RAG/Chroma'ya girmez. RAG yalnızca değişmeyecek arşiv
bilgisi (bilanço metni, şirket profili, referans) için kullanılır; güncel
bildirim listesi bu sağlayıcıdan doğrudan gelir (2026-08-24 tarihli karar).

Resmî/belgelenmiş bir KAP API'si yoktur. Bu modül `pykap` (MIT lisanslı,
PyPI, github.com/cemsinano/pykap) kütüphanesini sarmalar. Kütüphane KAP'ın
kendi web sayfalarını ayrıştırır — resmî/onaylı bir kaynak değildir (aynı
çekince `yfinance_p.py`'de de var, AK 5.1). KAP bir düzenleyici kamu ifşa
sistemi olduğu için (telifli bir haber sitesi değil, resmî/kamuya açık
bilgi), veri niteliği bakımından risk daha düşüktür — ama KAP site yapısı
değişirse kütüphane sessizce kırılabilir; `ProviderError` bu durumu
PROVIDER_UNAVAILABLE'a çevirir, çağıran taraf çökmez.

Alan adları GERÇEK bir çağrıyla doğrulandı (2026-08-24, ASELS, 30 günlük
pencere). `get_expected_disclosure_list` DENENDİ ve YANLIŞ bulundu: o
fonksiyon geçmiş bildirimleri değil, GELECEKTE beklenen dosyalama takvimini
döndürüyor (`startDate`/`endDate` bir dosyalama penceresi, yayın tarihi
değil). Doğru fonksiyon `get_historical_disclosure_list` — örnek çıktı:

    {'publishDate': '04.08.2026 18:39:41', 'kapTitle': 'ASELSAN ...',
     'disclosureClass': 'FR', 'subject': 'Finansal Rapor', 'year': 2026,
     'ruleType': '6 Aylık', 'period': 2, 'disclosureIndex': 1643141,
     'stockCodes': 'ASELS', 'summary': None, ...}

`disclosureIndex` bir bildirime giden URL değil, sayısal bir kimliktir;
gerçek bildirim adresi `data/documents/README.md`'deki kaynak_url deseniyle
(`kap.org.tr/tr/Bildirim/{id}`) aynı kurala göre kurulur.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.providers.base import ProviderError

logger = logging.getLogger(__name__)

_YAYIN_TARIHI_BICIMI = "%d.%m.%Y %H:%M:%S"
_BILDIRIM_URL_SABLONU = "https://www.kap.org.tr/tr/Bildirim/{disclosure_index}"

# Bu iki soru pratikte hep aynı — kaç günlük pencerede arama yapılacağı.
# Tool imzasında dışarı açmıyoruz (çağıran ajan tarafında karmaşıklık
# yaratmasın diye); sonuç boş dönerse ajan zaten "bulunamadı" yolundan
# geçiyor, geniş bir varsayılan pencere bunu nadir kılıyor.
_VARSAYILAN_GUN_PENCERESI = 60


_PENCERE_TARIHI_BICIMI = "%d.%m.%Y"


@dataclass(frozen=True)
class KapDisclosure:
    ticker: str
    baslik: str
    tarih: datetime | None
    url: str | None
    ham: dict[str, Any]  # loglama/hata ayıklama için ham kayıt korunur


@dataclass(frozen=True)
class KapExpectedDisclosure:
    """Bir şirketin YAKLAŞAN bildirim penceresi.

    `KapDisclosure`'dan farkı: bu bir yayın değil, bir TAKVİM kaydı. KAP tek
    bir tarih değil, dosyalamanın yapılabileceği bir aralık yayımlıyor
    (ölçüldü, 2026-08-24 ASELS):

        {'kapTitle': 'ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.',
         'subject': 'Finansal Rapor', 'ruleTypeTerm': '9 Aylık',
         'startDate': '01.10.2026', 'endDate': '09.11.2026',
         'stockCode': None, 'year': 2026, ...}

    `stockCode` NULL geliyor — hisse kodu yanıtta yok, sorguyu attığımız
    ticker'dan taşınıyor. `son_tarih` (endDate) sunulur: kullanıcı için
    bağlayıcı olan gün odur.
    """

    ticker: str
    sirket: str
    konu: str
    donem: str | None
    baslangic: date | None
    son_tarih: date | None
    ham: dict[str, Any]


def _baslik_olustur(row: dict[str, Any]) -> str:
    """'Finansal Rapor' + '6 Aylık' -> 'Finansal Rapor (6 Aylık)'. `subject`
    tek başına jenerik (birçok şirkette aynı metin); `ruleType` dönemi
    ekleyerek ayırt edici kılar."""
    konu = row.get("subject") or "Başlıksız bildirim"
    donem = row.get("ruleType")
    return f"{konu} ({donem})" if donem else str(konu)


def _tarih_ayristir(ham: Any) -> datetime | None:
    if not ham:
        return None
    try:
        return datetime.strptime(str(ham), _YAYIN_TARIHI_BICIMI)
    except ValueError:
        logger.warning("kap_p: publishDate ayrıştırılamadı: %r", ham)
        return None


def _url_olustur(row: dict[str, Any]) -> str | None:
    disclosure_index = row.get("disclosureIndex")
    if not disclosure_index:
        return None
    return _BILDIRIM_URL_SABLONU.format(disclosure_index=disclosure_index)


def _kayitlara_cevir(sonuc: Any) -> list[dict[str, Any]]:
    """pykap pandas DataFrame ya da dict listesi dönebiliyor (ölçümle:
    `get_historical_disclosure_list` dict listesi döndü) — ikisini de aynı
    şekle indirger. Tanınmayan bir tip gelirse veri UYDURULMAZ, boş liste
    dönülür ve loglanır."""
    if hasattr(sonuc, "to_dict"):  # pandas.DataFrame
        return sonuc.to_dict(orient="records")
    if isinstance(sonuc, list):
        return sonuc
    logger.warning("kap_p: beklenmeyen donus tipi: %s", type(sonuc))
    return []


def satiri_bildirime_cevir(ticker: str, row: dict[str, Any]) -> KapDisclosure:
    """Ham pykap satırını `KapDisclosure`'a çevirir. Tool katmanından ayrı
    tutulur ki gerçek örnek verilerle ağsız test edilebilsin (bkz.
    tests/test_kap_provider.py)."""
    return KapDisclosure(
        ticker=ticker,
        baslik=_baslik_olustur(row),
        tarih=_tarih_ayristir(row.get("publishDate")),
        url=_url_olustur(row),
        ham=row,
    )


def _pencere_tarihi(ham: Any) -> date | None:
    """`"09.11.2026"` -> `date(2026, 11, 9)`. Ayrıştırılamazsa `None`."""
    if not ham:
        return None
    try:
        return datetime.strptime(str(ham), _PENCERE_TARIHI_BICIMI).date()
    except ValueError:
        logger.warning("kap_p: pencere tarihi ayrıştırılamadı: %r", ham)
        return None


def satiri_beklenene_cevir(ticker: str, row: dict[str, Any]) -> KapExpectedDisclosure:
    """Ham pykap satırını `KapExpectedDisclosure`'a çevirir. Saf fonksiyon —
    gerçek örnek satırla ağsız test edilir (tests/test_kap_provider.py)."""
    return KapExpectedDisclosure(
        ticker=ticker,
        sirket=str(row.get("kapTitle") or ticker),
        konu=str(row.get("subject") or "Bildirim"),
        donem=str(row["ruleTypeTerm"]) if row.get("ruleTypeTerm") else None,
        baslangic=_pencere_tarihi(row.get("startDate")),
        son_tarih=_pencere_tarihi(row.get("endDate")),
        ham=row,
    )


class KapProvider:
    """`pykap` opsiyonel bir bağımlılıktır (`backend/requirements.txt`'e
    eklendi); import burada, sınıf seviyesinde değil — bu sağlayıcı hiç
    çağrılmazsa (ör. testlerde) paket kurulu olmak zorunda kalmaz."""

    def fetch_latest_disclosures(
        self, ticker: str, limit: int = 5, *, gun_penceresi: int = _VARSAYILAN_GUN_PENCERESI
    ) -> list[KapDisclosure]:
        try:
            from pykap.bist import BISTCompany
        except ImportError as exc:
            raise ProviderError("kap", ticker, "pykap kurulu değil (`pip install pykap`)") from exc

        bugun = date.today()
        baslangic = bugun - timedelta(days=gun_penceresi)

        try:
            company = BISTCompany(ticker=ticker)
            sonuc = company.get_historical_disclosure_list(
                fromdate=baslangic.strftime("%Y-%m-%d"),
                todate=bugun.strftime("%Y-%m-%d"),
            )
        except Exception as exc:  # pykap kendi hatalarını çeşitli tiplerle atıyor
            raise ProviderError("kap", ticker, f"istek başarısız: {exc}") from exc

        satirlar = _kayitlara_cevir(sonuc)
        bildirimler = [satiri_bildirime_cevir(ticker, row) for row in satirlar]
        # En yeni en üstte: KAP'ın kendi sıralaması garanti değil (ölçümle
        # doğrulanmadı — tek kayıtlı örnekte gözlemlenemedi), bu yüzden
        # kendimiz sıralıyoruz. Tarihsiz kayıtlar (ayrıştırma başarısızsa)
        # sona atılır, listeden düşürülmez.
        bildirimler.sort(key=lambda b: b.tarih or datetime.min, reverse=True)
        return bildirimler[:limit]

    def fetch_expected_disclosures(
        self, tickers: list[str], *, limit: int = 5, sirket_basina: int = 3
    ) -> list[KapExpectedDisclosure]:
        """Verilen şirketlerin YAKLAŞAN bildirim takvimi, son tarihe göre sıralı.

        ŞİRKET BAŞINA BİR İSTEK: pykap'ın arayüzü tek tek ticker alıyor, toplu
        sorgu yok. Bu yüzden çağıran taraf listeyi dar tutmalı (kullanıcının
        hisse pozisyonları); otuz şirket için otuz istek atmak bir ekran
        kartına değmez.

        BİR ŞİRKETİN DÜŞMESİ DİĞERLERİNİ DÜŞÜRMEZ: tek tek yakalanır ve
        loglanır. Hepsi düşerse boş liste döner — çağıran taraf bunu "takvim
        alınamadı" olarak sunar.

        Geçmiş pencereler ELENİR: son tarihi bugünden önce olan kayıt takvimde
        işi yok. Tarihi ayrıştırılamayan kayıt da elenir; tarihsiz bir takvim
        satırı kullanıcıya hiçbir şey söylemez.
        """
        try:
            from pykap.bist import BISTCompany
        except ImportError as exc:
            raise ProviderError(
                "kap", ",".join(tickers), "pykap kurulu değil (`pip install pykap`)"
            ) from exc

        bugun = date.today()
        kayitlar: list[KapExpectedDisclosure] = []

        for ticker in tickers:
            try:
                sonuc = BISTCompany(ticker=ticker).get_expected_disclosure_list(count=sirket_basina)
            except Exception as exc:  # pykap hatalarını çeşitli tiplerle atıyor
                logger.warning("kap_p: %s icin beklenen bildirim alinamadi: %s", ticker, exc)
                continue

            for row in _kayitlara_cevir(sonuc):
                kayit = satiri_beklenene_cevir(ticker, row)
                if kayit.son_tarih is not None and kayit.son_tarih >= bugun:
                    kayitlar.append(kayit)

        kayitlar.sort(key=lambda k: k.son_tarih or date.max)
        return kayitlar[:limit]
