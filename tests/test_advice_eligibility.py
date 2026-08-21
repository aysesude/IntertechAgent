"""Varlık sınıfı tavsiye uygunluğu testleri — iş analisti şartnamesi (2026-08).

Şartnamedeki tablo (NAKIT 1, TAHVIL 3, DOVIZ 4, ALTIN 4, HISSE 6) ve kural
("seviye puandan büyükse tavsiye alamaz") burada birebir kilitleniyor.
Beklenen değerler tabloya bakılarak ELLE yazıldı; koddan türetilmedi —
tablo yanlışlıkla değiştirilirse test bunu yakalamalı, sessizce uyum
sağlamamalı.
"""

import pytest

from app.core.config import AssetClass
from app.services.advice_eligibility import (
    allowed_asset_classes,
    blocked_asset_classes,
    is_advice_allowed,
    validate_survey_score,
)

# Puan -> tavsiye edilebilecek sınıflar. Şartnamedeki tablodan elle çıkarıldı.
_BEKLENEN = {
    1: {AssetClass.CASH},
    2: {AssetClass.CASH},
    3: {AssetClass.CASH, AssetClass.BOND},
    4: {AssetClass.CASH, AssetClass.BOND, AssetClass.CURRENCY, AssetClass.PRECIOUS_METAL},
    5: {AssetClass.CASH, AssetClass.BOND, AssetClass.CURRENCY, AssetClass.PRECIOUS_METAL},
    6: set(AssetClass),
    7: set(AssetClass),
}


@pytest.mark.parametrize("puan,beklenen", sorted(_BEKLENEN.items()))
def test_allowed_asset_classes_matches_specification(puan, beklenen):
    assert allowed_asset_classes(puan) == beklenen


@pytest.mark.parametrize("puan,beklenen", sorted(_BEKLENEN.items()))
def test_blocked_is_the_complement_of_allowed(puan, beklenen):
    assert blocked_asset_classes(puan) == set(AssetClass) - beklenen


def test_stock_advice_requires_score_six():
    """Hisse seviyesi 6: 5 ve altı puanlar hisse tavsiyesi alamaz."""
    assert not is_advice_allowed(AssetClass.STOCK, 5)
    assert is_advice_allowed(AssetClass.STOCK, 6)
    assert is_advice_allowed(AssetClass.STOCK, 7)


def test_equal_level_is_allowed_not_blocked():
    """Kural "BÜYÜKSE alamaz" diyor; eşitlik serbesttir.

    Sınır hatası burada yön değiştirir: `<` yazılsaydı tahvil seviyesi (3)
    olan bir kullanıcı tahvil tavsiyesi alamazdı — şartnamenin tam tersi.
    """
    assert is_advice_allowed(AssetClass.BOND, 3)
    assert is_advice_allowed(AssetClass.CURRENCY, 4)
    assert is_advice_allowed(AssetClass.PRECIOUS_METAL, 4)


def test_cash_is_allowed_at_every_score():
    """Nakit seviyesi 1: en düşük puanda bile serbest kalmalı."""
    for puan in range(1, 8):
        assert is_advice_allowed(AssetClass.CASH, puan), puan


def test_allowed_set_grows_monotonically_with_score():
    """Puan arttıkça izin kümesi daralamaz.

    Ayrı bir değişmez: tablo elle düzenlenirken bir sınıfın seviyesi yanlış
    girilirse (ör. nakit 5 yapılırsa) küme büyümesi bozulur ve bu test
    tekil eşleşme testlerinden bağımsız olarak uyarır.
    """
    for puan in range(1, 7):
        assert allowed_asset_classes(puan) <= allowed_asset_classes(puan + 1)


@pytest.mark.parametrize("gecersiz", [0, -1, 8, 100])
def test_out_of_range_score_raises(gecersiz):
    """Aralık dışı puan sessizce sınıra çekilmez, hata verir.

    Clamp edilseydi 9 puanlık bozuk bir girdi 7 sayılıp kullanıcıya hak
    etmediği genişlikte tavsiye üretilirdi.
    """
    with pytest.raises(ValueError):
        validate_survey_score(gecersiz)
    with pytest.raises(ValueError):
        allowed_asset_classes(gecersiz)
    with pytest.raises(ValueError):
        is_advice_allowed(AssetClass.CASH, gecersiz)


def test_specification_table_covers_every_asset_class():
    """Yeni bir varlık sınıfı eklenirse tablo da güncellenmeli.

    config.py açılışta bunu zaten doğruluyor; burada ikinci kez kontrol
    edilmesinin sebebi, o doğrulamanın yanlışlıkla kaldırılması durumunda
    testin sessiz kalmaması.
    """
    assert set(allowed_asset_classes(7)) == set(AssetClass)
