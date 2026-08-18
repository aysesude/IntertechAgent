"""Sentetik günlük fiyat serileri (source='synthetic').

Üç bileşenli faktör modeli:

    getiri = drift + vol × ( √m·PİYASA + √c·SINIF + √i·GÜRÜLTÜ )

Bağımsız random walk'lar varlıklar arası korelasyonu sıfır yapıyordu; bu,
gerçekte olmayan bir çeşitlendirme avantajı yaratıp risk skorunu ayrıştıramaz
hale getirmişti (ilk incelemenin ana bulgusu). Faktör modeli toplam
volatiliteyi değiştirmeden varlıkları birlikte hareket ettirir.

PİYASA faktörü mümkünse GERÇEK USDTRY getirilerinden alınır (price_history'de
sentetik olmayan USDTRY serisi varsa): böylece sentetik kalan varlıklar
(tahvil, mevduat) gerçek verili varlıklarla da gerçekçi korelasyon taşır —
karma evrendeki sıfır-korelasyon tuzağı kapanır.

Yalnızca İŞLEM GÜNLERİ (hafta içi) üretilir: gerçek kaynaklar hafta sonu fiyat
yayımlamaz; sentetiğin hafta sonu satır bırakması karma seride sahte
volatilite yaratır.

Yazma `price_ingest.upsert_prices` ile yapılır; sentetik, gerçek satırları
yapısal olarak EZEMEZ. Yeniden üretim öncesi eski sentetik satırlar silinir
(sentetik-sentetik çakışması öncelik kuralına takılır; parametre değişikliği
ancak silmeyle yansır).
"""

import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import AssetClass, PriceSource, settings
from app.models import Asset, PriceHistory
from app.providers.base import PricePoint
from app.providers.universe import ASSET_UNIVERSE, AssetSpec
from app.services.price_ingest import upsert_prices

SEED = 42
HISTORY_DAYS = 365  # takvim günü; içinden hafta içi günler kullanılır

# Varlık sınıfı başına (günlük drift, günlük volatilite).
ASSET_CLASS_DAILY_DRIFT_VOLATILITY: dict[AssetClass, tuple[float, float]] = {
    AssetClass.STOCK: (0.0004, 0.020),
    AssetClass.PRECIOUS_METAL: (0.0002, 0.008),
    AssetClass.CURRENCY: (0.0001, 0.006),
    AssetClass.BOND: (0.00015, 0.003),
    AssetClass.CASH: (0.0, 0.0),  # birim fiyat sabit 1; getiri INTEREST ile deftere yazılır
}

# Varyans payları (piyasa, sınıf, varlığa özgü) — toplamı 1.
# Hedef korelasyonlar: hisse-hisse ~0.60, döviz-döviz ~0.85, altın-döviz ~0.47.
ASSET_CLASS_FACTOR_SHARES: dict[AssetClass, tuple[float, float, float]] = {
    AssetClass.STOCK: (0.30, 0.30, 0.40),
    AssetClass.PRECIOUS_METAL: (0.50, 0.20, 0.30),
    AssetClass.CURRENCY: (0.45, 0.40, 0.15),
    AssetClass.BOND: (0.25, 0.35, 0.40),
    AssetClass.CASH: (0.0, 0.0, 1.0),
}

_PRICE_QUANT = Decimal("0.000001")


def trading_days(end: date, history_days: int = HISTORY_DAYS) -> list[date]:
    """[end - history_days + 1, end] aralığındaki hafta içi günler."""
    start = end - timedelta(days=history_days - 1)
    return [
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    ]


def _real_usdtry_market_factor(session: Session, days: list[date]) -> list[float] | None:
    """Gerçek USDTRY getirilerinden standardize piyasa faktörü; veri yoksa None."""
    asset_id = session.execute(
        select(Asset.id).where(Asset.symbol == "USDTRY")
    ).scalar_one_or_none()
    if asset_id is None:
        return None
    rows = (
        session.execute(
            select(PriceHistory.close_price)
            .where(
                PriceHistory.asset_id == asset_id,
                PriceHistory.source != PriceSource.SYNTHETIC,
            )
            .order_by(PriceHistory.price_date)
        )
        .scalars()
        .all()
    )
    if len(rows) < 30:  # anlamlı bir dağılım için alt sınır
        return None

    returns = [float(rows[i] / rows[i - 1]) - 1.0 for i in range(1, len(rows)) if rows[i - 1] > 0]
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns)) or 1.0
    standardized = [(r - mean) / std for r in returns]
    # Gerekli gün sayısına döngüyle uzatılır (deterministik).
    needed = len(days) - 1
    return [standardized[i % len(standardized)] for i in range(needed)]


def generate_synthetic_series(
    spec: AssetSpec, days: list[date], market_path: list[float]
) -> dict[date, Decimal]:
    """Tek varlığın fiyat serisi. Sınıf faktörü yolunun deterministik olması
    için sınıf başına türetilmiş ayrı bir rng kullanılır (çağrı sırasından
    bağımsız)."""
    drift, vol = ASSET_CLASS_DAILY_DRIFT_VOLATILITY[spec.asset_class]
    market_share, class_share, idio_share = ASSET_CLASS_FACTOR_SHARES[spec.asset_class]

    class_rng = random.Random(f"{SEED}:{spec.asset_class.value}")
    class_path = [class_rng.gauss(0, 1) for _ in range(len(days) - 1)]
    idio_rng = random.Random(f"{SEED}:{spec.symbol}")

    price = spec.base_price
    series = {days[0]: price.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)}
    for i in range(1, len(days)):
        shock = (
            math.sqrt(market_share) * market_path[i - 1]
            + math.sqrt(class_share) * class_path[i - 1]
            + math.sqrt(idio_share) * idio_rng.gauss(0, 1)
        )
        daily_return = drift + vol * shock
        price = price * (Decimal(1) + Decimal(str(round(daily_return, 8))))
        price = max(price, Decimal("0.01")).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
        series[days[i]] = price
    return series


def seed_prices_synthetic(session: Session, assets_by_symbol: dict[str, Asset]) -> int:
    """Tüm varlıklar için sentetik seri üretir; yazılan satır sayısını döndürür.

    Gerçek verisi olan varlıklar için de üretilir (çevrimdışı çalışabilirlik,
    A1); upsert önceliği gerçek satırlara dokunulmamasını garanti eder.
    Türetilmiş varlıkların (sikke) sentetiği, kaynağının sentetiğinden
    katsayıyla hesaplanır ki sentetik evren kendi içinde tutarlı olsun.
    """
    anchor = settings.anchor_date
    days = trading_days(anchor)

    # Yeniden üretim: yalnızca sentetik satırlar silinir (gerçek veri korunur).
    session.execute(delete(PriceHistory).where(PriceHistory.source == PriceSource.SYNTHETIC))
    session.flush()

    market_path = _real_usdtry_market_factor(session, days)
    if market_path is None:
        market_rng = random.Random(f"{SEED}:market")
        market_path = [market_rng.gauss(0, 1) for _ in range(len(days) - 1)]

    series_by_symbol: dict[str, dict[date, Decimal]] = {}
    total_rows = 0

    base_specs = [s for s in ASSET_UNIVERSE if s.derived_from is None]
    derived_specs = [s for s in ASSET_UNIVERSE if s.derived_from is not None]

    for spec in base_specs:
        series_by_symbol[spec.symbol] = generate_synthetic_series(spec, days, market_path)
    for spec in derived_specs:
        base_series = series_by_symbol[spec.derived_from]
        series_by_symbol[spec.symbol] = {
            d: (p * spec.derived_factor).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
            for d, p in base_series.items()
        }

    for symbol, series in series_by_symbol.items():
        points = [
            PricePoint(price_date=d, close_price=p, source=PriceSource.SYNTHETIC)
            for d, p in series.items()
        ]
        total_rows += upsert_prices(session, assets_by_symbol[symbol].id, points)

    session.flush()
    return total_rows
