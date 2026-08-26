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


@dataclass(frozen=True)
class KapDisclosure:
    ticker: str
    baslik: str
    tarih: datetime | None
    url: str | None
    ham: dict[str, Any]  # loglama/hata ayıklama için ham kayıt korunur


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
