"""app/services/target_price_ingest.py: target_prices'a yazan TEK taraf.

Kurum başına TEK satır (tarihçe değil) — bkz. modül docstring'i. Bu testler
upsert davranışını ve revizyon hesabını (previous_target_price/
revision_direction) doğrudan doğrular.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import AssetClass
from app.models import Asset, TargetPrice
from app.providers.base import TargetPricePoint
from app.services.target_price_ingest import upsert_target_prices


@pytest.fixture()
def garan(db_session):
    asset = Asset(symbol="GARAN", name="Garanti BBVA", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(asset)
    db_session.flush()
    return asset


def _nokta(symbol: str, hedef: str, **kwargs) -> TargetPricePoint:
    varsayilan = {
        "symbol": symbol,
        "institution": "Şeker Yatırım",
        "recommendation": "AL",
        "target_price": Decimal(hedef),
        "currency": "TRY",
        "price_at_report": Decimal("133.00"),
        "report_date": date(2026, 8, 28),
        "source_url": "https://example.com",
    }
    varsayilan.update(kwargs)
    return TargetPricePoint(**varsayilan)


def test_ilk_ingest_yeni_satir_yazar(db_session, garan):
    yazilan = upsert_target_prices(db_session, [_nokta("GARAN", "182.99")])
    assert yazilan == 1

    satir = db_session.query(TargetPrice).filter_by(asset_id=garan.id).one()
    assert satir.target_price == Decimal("182.990000")
    assert satir.previous_target_price is None
    assert satir.revision_direction is None


def test_tekrar_ingest_ayni_hedefle_yeni_satir_eklemez(db_session, garan):
    upsert_target_prices(db_session, [_nokta("GARAN", "182.99")])
    upsert_target_prices(db_session, [_nokta("GARAN", "182.99")])

    satirlar = db_session.query(TargetPrice).filter_by(asset_id=garan.id).all()
    assert len(satirlar) == 1


def test_hedef_degisince_revizyon_alanlari_doldurulur(db_session, garan):
    """Doküman: "hedef yükseltildi mi düşürüldü mü" sorusu, hedefin
    kendisinden daha bilgilendirici — bu yüzden eski değer korunuyor."""
    upsert_target_prices(db_session, [_nokta("GARAN", "182.99")])
    upsert_target_prices(db_session, [_nokta("GARAN", "200.00")])

    satir = db_session.query(TargetPrice).filter_by(asset_id=garan.id).one()
    assert satir.target_price == Decimal("200.000000")
    assert satir.previous_target_price == Decimal("182.990000")
    assert satir.revision_direction == "yukseltme"


def test_hedef_dusunce_dusurme_isaretlenir(db_session, garan):
    upsert_target_prices(db_session, [_nokta("GARAN", "182.99")])
    upsert_target_prices(db_session, [_nokta("GARAN", "150.00")])

    satir = db_session.query(TargetPrice).filter_by(asset_id=garan.id).one()
    assert satir.revision_direction == "dusurme"


def test_bilinmeyen_sembol_atlanir_hata_vermez(db_session, garan):
    """Varlık evreninde olmayan bir sembol (kaynak GARAN'ın yanında
    tanımadığımız bir hisse de döndürdüyse) sessizce atlanır — CLAUDE.md
    "zarif düşüş"."""
    yazilan = upsert_target_prices(
        db_session, [_nokta("GARAN", "182.99"), _nokta("BILINMEYEN", "50.00")]
    )
    assert yazilan == 1
    assert db_session.query(TargetPrice).count() == 1


def test_bos_liste_hicbir_sey_yazmaz(db_session):
    assert upsert_target_prices(db_session, []) == 0
