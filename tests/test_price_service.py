"""price_service.get_asset_price_history testleri.

Vurgu kısmi veri politikasında: bir sembolün verisinin olmaması diğerlerinin
serisini engellemez, eldeki kadarı döner ve eksiklik ayrıca raporlanır.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import AssetClass, Granularity, PriceCurrency, TimeWindow
from app.core.exceptions import InsufficientDataError, NotFoundError, ValidationAppError
from app.models import Asset, PriceHistory
from app.services.price_service import get_asset_price_history, resolve_granularity

# 2026-01-03 Cumartesi: seride gorunmemeli.
GUNLER = [
    date(2026, 1, 1),
    date(2026, 1, 2),
    date(2026, 1, 3),
    date(2026, 1, 5),
    date(2026, 1, 9),
]


@pytest.fixture()
def price_fixture(db_session):
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    foreign = Asset(
        symbol="FRGN", name="Yabanci Hisse", asset_class=AssetClass.STOCK, currency="USD"
    )
    usdtry = Asset(
        symbol="USDTRY", name="Amerikan Dolari", asset_class=AssetClass.CURRENCY, currency="TRY"
    )
    old = Asset(symbol="OLD", name="Eski Veri", asset_class=AssetClass.BOND, currency="TRY")
    empty = Asset(symbol="EMPTY", name="Hic Veri Yok", asset_class=AssetClass.BOND, currency="TRY")
    db_session.add_all([stock, foreign, usdtry, old, empty])
    db_session.flush()

    rows = []
    for i, gun in enumerate(GUNLER):
        rows.append(PriceHistory(asset_id=stock.id, price_date=gun, close_price=Decimal(100 + i)))
        rows.append(PriceHistory(asset_id=foreign.id, price_date=gun, close_price=Decimal(10)))
        rows.append(PriceHistory(asset_id=usdtry.id, price_date=gun, close_price=Decimal(40)))
    # Pencerenin cok oncesi: taninir ama seride yer almaz.
    rows.append(PriceHistory(asset_id=old.id, price_date=date(2025, 1, 6), close_price=Decimal(5)))
    db_session.add_all(rows)
    db_session.commit()
    return stock


def test_price_history_drops_weekends_and_reports_actual_start(db_session, price_fixture):
    result = get_asset_price_history(db_session, ["TST"], window=TimeWindow.M1)

    gunler = [point.date for point in result.series["TST"]]
    assert date(2026, 1, 3) not in gunler  # Cumartesi
    assert gunler == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 9)]
    assert result.as_of == date(2026, 1, 9)
    assert result.actual_start == date(2026, 1, 1)
    # Istenen baslangic penceresi gercek baslangictan geride: kismi veri.
    assert result.requested_start < result.actual_start


def test_price_history_converts_to_try_with_that_days_rate(db_session, price_fixture):
    donusmus = get_asset_price_history(
        db_session, ["FRGN"], window=TimeWindow.M1, currency=PriceCurrency.TRY
    )
    ham = get_asset_price_history(
        db_session, ["FRGN"], window=TimeWindow.M1, currency=PriceCurrency.NATIVE
    )

    # 10 USD x 40 TL/USD = 400 TL; NATIVE'de cevrim yapilmaz.
    assert donusmus.series["FRGN"][0].close == Decimal("400.00")
    assert ham.series["FRGN"][0].close == Decimal("10.00")


def test_price_history_partial_data_is_not_an_error(db_session, price_fixture):
    result = get_asset_price_history(db_session, ["TST", "OLD", "YOKBOYLE"], window=TimeWindow.M1)

    # Bir sembolun eksikligi digerinin serisini engellemez.
    assert "TST" in result.series
    assert result.symbols_without_data == ["OLD"]
    assert result.unknown_symbols == ["YOKBOYLE"]


def test_price_history_raises_when_nothing_is_known_or_stored(db_session, price_fixture):
    with pytest.raises(ValidationAppError):
        get_asset_price_history(db_session, [])

    with pytest.raises(NotFoundError):
        get_asset_price_history(db_session, ["HICBIRI"])

    # Varlik taniniyor ama tabloda tek fiyat yok (make backfill hic kosmamis).
    with pytest.raises(InsufficientDataError):
        get_asset_price_history(db_session, ["EMPTY"])


def test_resolve_granularity_follows_window_but_respects_explicit_choice():
    assert resolve_granularity(TimeWindow.M3, Granularity.AUTO) is Granularity.DAILY
    assert resolve_granularity(TimeWindow.M12, Granularity.AUTO) is Granularity.WEEKLY
    # Risk tarafi DAILY istemek zorunda; acik secim ezilmez.
    assert resolve_granularity(TimeWindow.M12, Granularity.DAILY) is Granularity.DAILY
