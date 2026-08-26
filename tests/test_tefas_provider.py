"""TEFAS sağlayıcısının fiyat süzme davranışı.

Buradaki asıl mesele bir veri tuzağı: TEFAS, fonun KURULUŞUNDAN ÖNCEKİ
tarihler için `0.0` döndürüyor. Hata değil, "o gün bu fon henüz yoktu"
demenin biçimi — ama sıfır bir fiyat gibi ingest edilirse zinciri baştan
sona bozar.

Ölçüldü (25 Ağustos 2026, gerçek TEFAS): A1 Capital para piyasası fonuna
365 günlük istek atıldığında 227 satırın **14'ü sıfır** geldi. Mevcut dokuz
fonda tetiklenmiyor çünkü hepsinin geçmişi pencereden uzun; genç bir fon
eklendiği anda devreye girer.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.providers.base import ProviderError
from app.providers.tefas_p import TefasProvider


class _SahteCrawler:
    """`tefas.Crawler` yerine geçer; `fetch` sabit bir çerçeve döndürür."""

    def __init__(self, satirlar):
        self._satirlar = satirlar

    def fetch(self, **kwargs):
        import pandas as pd

        return pd.DataFrame(self._satirlar)


@pytest.fixture()
def _sahte_tefas(monkeypatch):
    """`from tefas import Crawler` çağrısını yakalar.

    Sağlayıcı import'u fonksiyonun İÇİNDE yapıyor (kütüphane kurulu değilse
    anlamlı hata versin diye), o yüzden modülü sys.modules'e koymak gerekiyor.
    """
    import sys
    import types

    def _kur(satirlar):
        sahte = types.ModuleType("tefas")
        sahte.Crawler = lambda *a, **k: _SahteCrawler(satirlar)
        monkeypatch.setitem(sys.modules, "tefas", sahte)

    return _kur


def test_kurulus_oncesi_SIFIR_fiyatlar_atilir(_sahte_tefas):
    """Sıfır fiyat `price_history`'ye YAZILMAMALI.

    Yazılsaydı: portföy o gün 0 TL değerlenir, günlük getiri sıfıra bölünür
    ve 0 -> 1,40 geçişi volatiliteyi uçururdu.
    """
    _sahte_tefas(
        [
            {"date": date(2026, 1, 1), "price": 0.0},
            {"date": date(2026, 1, 2), "price": 0.0},
            {"date": date(2026, 1, 5), "price": 1.4021},
            {"date": date(2026, 1, 6), "price": 1.4055},
        ]
    )

    noktalar = TefasProvider().fetch_series("IOO", date(2026, 1, 1), date(2026, 1, 6))

    assert [p.price_date for p in noktalar] == [date(2026, 1, 5), date(2026, 1, 6)]
    assert all(p.close_price > 0 for p in noktalar)


def test_negatif_fiyat_da_atilir(_sahte_tefas):
    """Fon fiyatı negatif olamaz; geldiyse veri bozuktur, taşınmaz."""
    _sahte_tefas(
        [
            {"date": date(2026, 1, 5), "price": -0.5},
            {"date": date(2026, 1, 6), "price": 1.4055},
        ]
    )

    noktalar = TefasProvider().fetch_series("IOO", date(2026, 1, 5), date(2026, 1, 6))

    assert [p.price_date for p in noktalar] == [date(2026, 1, 6)]


def test_gecerli_fiyatlar_bozulmadan_gecer(_sahte_tefas):
    """Süzgeç yalnızca sıfır/negatifi almalı, geçerli veriye dokunmamalı."""
    _sahte_tefas(
        [
            {"date": date(2026, 1, 6), "price": 1.405512},
            {"date": date(2026, 1, 5), "price": 1.402100},
        ]
    )

    noktalar = TefasProvider().fetch_series("IOO", date(2026, 1, 5), date(2026, 1, 6))

    # Tarihe göre sıralanmış olmalı (seri tüketicileri buna güveniyor).
    assert [p.price_date for p in noktalar] == [date(2026, 1, 5), date(2026, 1, 6)]
    assert noktalar[1].close_price == Decimal("1.405512")


def test_HEPSI_sifirsa_veri_yok_hatasi(_sahte_tefas):
    """Fon henüz kurulmamışsa "veri dönmedi" demek doğru davranış.

    Sessizce boş liste dönmek, çağıranın (backfill) bunu başarı sanmasına ve
    o sembolü bir daha denememesine yol açardı.
    """
    _sahte_tefas(
        [
            {"date": date(2026, 1, 1), "price": 0.0},
            {"date": date(2026, 1, 2), "price": 0.0},
        ]
    )

    with pytest.raises(ProviderError):
        TefasProvider().fetch_series("YENI", date(2026, 1, 1), date(2026, 1, 2))
