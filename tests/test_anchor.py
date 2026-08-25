"""Ankraj çözümlemesi — seed'in "bugün"ü nereden geliyor.

Ankraj eskiden sabit bir tarihti (2026-08-01). Gerçek fiyatlar günlük toplama
işiyle ilerlemeye devam ettiği için "son işlem" ile "son fiyat" arasındaki
açık HER GÜN BİR GÜN büyüyordu — 23 Ağustos'ta 21 güne çıkmıştı ve kullanıcı
"Son İşlemler" listesinde üç haftalık kayıtlar görüyordu. Kapatmak için
birinin `.env`'i elle güncelleyip yeniden seed etmesi gerekiyordu.

Buradaki testler ankrajın artık kendini gerçek veriye bağladığını ve override
yolunun sağlam kaldığını koruyor.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import AssetClass, PriceSource, settings
from app.models import Asset, PriceHistory
from data.anchor import resolve_anchor_date, son_is_gunu


@pytest.fixture()
def _ankraj_serbest(monkeypatch):
    """Override YOKMUŞ gibi davranır (`settings.anchor_date is None`).

    Ortam değişkenini silmek YETMEZ: `Settings` açılışta bir kez okunuyor ve
    `data/anchor.py` o tekil nesneye bağlı. Alanı doğrudan yamalamak, env
    değişkeninin hiç verilmediği durumun birebir karşılığı.

    conftest testler için ankrajı sabitliyor; bu modül tam olarak override
    yokken ne olduğunu sınadığı için onu geri alması gerekiyor.
    """
    monkeypatch.setattr(settings, "anchor_date", None)


def _fiyat_ekle(session, symbol: str, gun: date, kaynak: PriceSource) -> None:
    asset = session.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
    if asset is None:
        asset = Asset(symbol=symbol, name=symbol, asset_class=AssetClass.STOCK, currency="TRY")
        session.add(asset)
        session.flush()
    session.add(
        PriceHistory(asset_id=asset.id, price_date=gun, close_price=Decimal("100"), source=kaynak)
    )
    session.flush()


class TestSonIsGunu:
    def test_hafta_ici_gun_degismez(self):
        # 2026-08-19 Çarşamba
        assert son_is_gunu(date(2026, 8, 19)) == date(2026, 8, 19)

    def test_cumartesi_cumaya_ceker(self):
        assert son_is_gunu(date(2026, 8, 22)) == date(2026, 8, 21)

    def test_pazar_cumaya_ceker(self):
        assert son_is_gunu(date(2026, 8, 23)) == date(2026, 8, 21)


class TestAnkrajCozumleme:
    def test_ANCHOR_DATE_verilmisse_her_seyi_ezer(self, db_session, monkeypatch):
        """Override yolu testlerin ve yeniden üretilebilir koşuların dayanağı.

        Gerçek fiyat verisi VARKEN bile override kazanmalı; aksi halde
        sabitlemek isteyen bir koşu sessizce kayardı.
        """
        monkeypatch.setattr(settings, "anchor_date", date(2026, 3, 15))
        _fiyat_ekle(db_session, "TSTA", date(2026, 8, 20), PriceSource.YFINANCE)

        assert resolve_anchor_date(db_session) == date(2026, 3, 15)

    def test_override_yoksa_son_GERCEK_fiyat_gunune_baglanir(self, db_session, _ankraj_serbest):
        _fiyat_ekle(db_session, "TSTB", date(2026, 8, 18), PriceSource.YFINANCE)
        _fiyat_ekle(db_session, "TSTB", date(2026, 8, 20), PriceSource.TCMB)

        assert resolve_anchor_date(db_session) == date(2026, 8, 20)

    def test_SENTETIK_satirlar_ankraji_ILERLETMEZ(self, db_session, _ankraj_serbest):
        """Sentetik fiyatlar sayılsaydı ankraj kendi kuyruğunu yerdi.

        Sentetik serinin son günü zaten bir önceki ankrajdan geliyor; onu
        ölçüt alsaydık ankraj hiç ilerlemez, her seed aynı günde kalırdı.
        """
        _fiyat_ekle(db_session, "TSTC", date(2026, 8, 18), PriceSource.YFINANCE)
        _fiyat_ekle(db_session, "TSTC", date(2026, 12, 31), PriceSource.SYNTHETIC)

        assert resolve_anchor_date(db_session) == date(2026, 8, 18)

    def test_hic_gercek_fiyat_yoksa_son_is_gunune_duser(self, db_session, _ankraj_serbest):
        """Temiz kurulum: `make backfill` hiç çalışmamış."""
        _fiyat_ekle(db_session, "TSTD", date(2026, 8, 18), PriceSource.SYNTHETIC)

        sonuc = resolve_anchor_date(db_session)

        assert sonuc.weekday() < 5, "hafta sonu ankraj olamaz"
        # Bugüne yakın olmalı; tam eşitlik testin koştuğu güne bağlı olurdu.
        assert abs((date.today() - sonuc).days) <= 4
