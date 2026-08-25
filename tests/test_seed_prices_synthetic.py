"""Sentetik/gerçek karışımının temizlenmesi — AK 5.1.

`test_data_layer.py`'deki invariantlar seed'li veriye bakar ve o veri (ağ
olmadığı için) tamamen sentetiktir; karışım senaryosu ancak elle kurulabilir.
Bu dosya `db_session` fixture'ını kullanıyor — teardown'ı tüm tabloları
sildiği için `test_data_layer.py`'nin modül kapsamlı seed'inden SONRA
koşmalı (dosya adı alfabetik olarak sonra geliyor).
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import AssetClass, PriceSource
from app.models import Asset, PriceHistory
from app.providers.base import PricePoint
from app.services.price_ingest import upsert_prices
from data.seed_prices_synthetic import (
    MIN_REAL_ROWS_FOR_PURE_REAL,
    drop_synthetic_where_real_exists,
)

_START = date(2026, 1, 5)  # Pazartesi


def _weekdays(count: int, start: date = _START) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _synthetic_days(db_session, asset_id) -> list[date]:
    return sorted(
        db_session.execute(
            select(PriceHistory.price_date).where(
                PriceHistory.asset_id == asset_id,
                PriceHistory.source == PriceSource.SYNTHETIC,
            )
        )
        .scalars()
        .all()
    )


def test_ak_5_1_drop_synthetic_removes_holes_and_prefix(db_session):
    """Gerçek kapsaması yeterli varlıkta sentetik satır hiç kalmamalı.

    Kurgu, canlıda ölçülen durumun küçültülmüş hâli: gerçek seri + ortasında
    tatil deliği + öncesinde sentetik geçmiş. Delik, `trading_days()` resmî
    tatilleri bilmediği için oluşuyor ve sentetik fiyat gerçekten kat kat
    sapabildiği için (ölçülen: 5,42 vs 35,63) sahte getiri ve sahte maliyet
    üretiyor.
    """
    asset = Asset(symbol="MIX", name="Karisim", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(asset)
    db_session.flush()

    real_days = _weekdays(MIN_REAL_ROWS_FOR_PURE_REAL + 5)
    hole = real_days.pop(10)
    prefix = [_START - timedelta(days=7), _START - timedelta(days=4)]

    upsert_prices(
        db_session,
        asset.id,
        [PricePoint(d, Decimal("100.00"), PriceSource.YFINANCE) for d in real_days],
    )
    upsert_prices(
        db_session,
        asset.id,
        [PricePoint(d, Decimal("5.00"), PriceSource.SYNTHETIC) for d in [hole, *prefix]],
    )
    db_session.flush()

    removed = drop_synthetic_where_real_exists(db_session)
    db_session.flush()

    assert removed == 3, "delik + öncesindeki iki gün silinmeliydi"
    assert _synthetic_days(db_session, asset.id) == []

    surviving = db_session.execute(
        select(func.count()).select_from(PriceHistory).where(PriceHistory.asset_id == asset.id)
    ).scalar_one()
    assert surviving == len(real_days), "gerçek satırlara dokunulmamalı"


def test_thin_real_coverage_keeps_prefix_history(db_session):
    """Gerçek satırı az olan varlıkta yalnızca delik silinir.

    Yeni eklenmiş ya da backfill'i yarım kalmış bir varlığın sentetik geçmişi
    tamamen silinseydi risk penceresi boşalırdı; karışım tehlikesi ise
    yalnızca gerçek aralığın İÇİNDE var.
    """
    asset = Asset(symbol="THIN", name="Az Veri", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(asset)
    db_session.flush()

    real_days = _weekdays(5)
    hole = real_days.pop(2)
    prefix = [_START - timedelta(days=7), _START - timedelta(days=4)]

    upsert_prices(
        db_session,
        asset.id,
        [PricePoint(d, Decimal("100.00"), PriceSource.YFINANCE) for d in real_days],
    )
    upsert_prices(
        db_session,
        asset.id,
        [PricePoint(d, Decimal("5.00"), PriceSource.SYNTHETIC) for d in [hole, *prefix]],
    )
    db_session.flush()

    removed = drop_synthetic_where_real_exists(db_session)
    db_session.flush()

    assert removed == 1, "yalnızca aralık içindeki delik silinmeli"
    assert _synthetic_days(db_session, asset.id) == sorted(prefix)


def test_fully_synthetic_asset_is_untouched(db_session):
    """Hiç gerçek verisi olmayan varlık (mevduat) etkilenmemeli."""
    asset = Asset(symbol="ONLYSYN", name="Mevduat", asset_class=AssetClass.CASH, currency="TRY")
    db_session.add(asset)
    db_session.flush()

    days = _weekdays(10)
    upsert_prices(
        db_session,
        asset.id,
        [PricePoint(d, Decimal("1.00"), PriceSource.SYNTHETIC) for d in days],
    )
    db_session.flush()

    assert drop_synthetic_where_real_exists(db_session) == 0
    assert _synthetic_days(db_session, asset.id) == days


# --------------------------------------------------------------------------
# Varlık bazlı sentetik parametre ezmesi
# --------------------------------------------------------------------------


def test_varlik_bazli_drift_sinif_varsayilanini_ezer():
    """Para piyasası fonu, BOND sınıf varsayılanıyla yetinmez.

    Getirisini FİYATI üzerinden biriktirir ve gerçek oynaklığı borçlanma
    fonlarınınkinden düşüktür (ölçülen: %1,42 yıllık). Sınıf varsayılanı
    kullanılsaydı çevrimdışı modda yanlış mertebede bir seri üretilirdi.
    """
    from app.core.config import PriceSource
    from app.providers.universe import SPEC_BY_SYMBOL
    from data.seed_prices_synthetic import generate_synthetic_series, trading_days

    ioo = SPEC_BY_SYMBOL["IOO"]

    assert ioo.synthetic_daily_drift is not None, "para piyasası fonu sınıf varsayılanını ezmeli"
    assert ioo.data_source is PriceSource.TEFAS

    days = trading_days(date(2026, 8, 3), history_days=200)
    market_path = [0.0] * (len(days) - 1)

    seri = generate_synthetic_series(ioo, days, market_path)

    assert seri[days[-1]] > seri[days[0]], "para piyasası fonu getiri biriktirmeli"


def test_bond_sinifi_kusuratli_adet_alir():
    """Tahvil sınıfının tamamı artık fon; fonlar küsuratlı alınır.

    Doğrudan tahvil adet bazlı alınır ve BOND tam sayıydı. PR #46 sonrası
    sınıfta yalnızca TEFAS borçlanma araçları fonları var ve birim fiyatları
    0,14 TL mertebesinde — tam sayıya yuvarlamak gereksiz sapma bırakıyordu.
    """
    from app.core.config import AssetClass, PriceSource
    from app.providers.universe import ASSET_UNIVERSE
    from data.seed_ledger import QUANTITY_PRECISION

    bond_specs = [s for s in ASSET_UNIVERSE if s.asset_class is AssetClass.BOND]
    assert bond_specs, "tahvil sınıfı boş"
    assert all(
        s.data_source is PriceSource.TEFAS for s in bond_specs
    ), "sınıfa doğrudan tahvil eklendiyse adet hassasiyeti yeniden düşünülmeli"
    assert QUANTITY_PRECISION[AssetClass.BOND] == Decimal("0.01")


def test_fon_base_price_gercek_fiyatla_ayni_mertebede():
    """`base_price` uydurulmamalı; gerçek fiyatın mertebesinde olmalı.

    Fon değerleri bir kez uydurulmuştu ve kat kat sapıyordu (`TI2` 2,1450
    yazılıydı, gerçek fiyatı 0,11 — 20 kat). Gerçek verinin bulunduğu ortamda
    zararsızdı (upsert eziyordu), ama backfill koşmamış bir kurulumda
    gerçekle alakasız bir evren üretiyordu.

    Buradaki değerler 21 Ağustos 2026'da ölçüldü (serinin ilk gerçek günü).
    Fon fiyatları zamanla değişir ama BAŞLANGIÇ fiyatı sabittir; bu test
    kırılırsa `base_price` elle değiştirilmiş demektir.
    """
    from app.providers.universe import SPEC_BY_SYMBOL

    olculen = {
        "AFT": "0.669568",
        "AK2": "0.435853",
        "AKE": "0.430407",
        "APT": "0.122145",
        "AYR": "0.095774",
        "GTA": "1.078670",
        "IOO": "3.154068",
        "TCD": "35.646015",
        "TI2": "0.110169",
    }
    for symbol, deger in olculen.items():
        assert SPEC_BY_SYMBOL[symbol].base_price == Decimal(
            deger
        ), f"{symbol}: base_price ölçülen ilk gerçek fiyattan farklı"
