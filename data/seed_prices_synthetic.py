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

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import AssetClass, PriceSource
from app.models import Asset, PriceHistory
from app.providers.base import PricePoint
from app.providers.universe import ASSET_UNIVERSE, AssetSpec
from app.services.price_ingest import upsert_prices
from data.anchor import resolve_anchor_date

SEED = 42
HISTORY_DAYS = 365  # takvim günü; içinden hafta içi günler kullanılır

# Bu kadar gerçek satırı olan varlık "gerçek verili" sayılır ve sentetik
# satırlarının TAMAMI silinir (bkz. drop_synthetic_where_real_exists). ~6 hafta:
# risk penceresinin anlamlı çalışabileceği en küçük geçmiş. Altındaki
# varlıklarda yalnızca gerçek aralığın içindeki delikler temizlenir.
MIN_REAL_ROWS_FOR_PURE_REAL = 30

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
    # Sınıf varsayılanı, varlık kendi değerini vermişse ezilir. Gerekçesi
    # AssetSpec.synthetic_daily_drift'te yazılı: bir varlık sınıfının tipik
    # davranışından ayrılabiliyor (para piyasası fonu CASH sınıfındadır ama
    # mevduat gibi sabit durmaz).
    class_drift, class_vol = ASSET_CLASS_DAILY_DRIFT_VOLATILITY[spec.asset_class]
    drift = class_drift if spec.synthetic_daily_drift is None else spec.synthetic_daily_drift
    vol = class_vol if spec.synthetic_daily_volatility is None else spec.synthetic_daily_volatility
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
    anchor = resolve_anchor_date(session)
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
    total_rows -= drop_synthetic_where_real_exists(session)
    session.flush()
    return total_rows


def drop_synthetic_where_real_exists(session: Session) -> int:
    """Gerçek veriyle iç içe geçmiş sentetik satırları siler; silinen sayıyı döndürür.

    NEDEN GEREKLİ. `trading_days()` yalnızca hafta sonunu eler, resmî tatilleri
    bilmez. BIST/TEFAS tatilde fiyat yayımlamaz, dolayısıyla gerçek serinin
    ORTASINDA sentetik satırlar kalıyordu — üzerlerine yazacak gerçek satır
    olmadığı için öncelik kuralı devreye girmiyor. Ölçülen: 35 varlığın
    hepsinde 2-10 arası "delik", ayrıca gerçek serinin öncesinde 13 gün.

    Sentetik `base_price` gerçek fiyattan kat kat sapabildiği için (TCD: 5,42
    vs gerçek 35,63; PPF: 118,50 vs gerçek 3,50-5,17) her delik şunları üretir:

    - **Sahte günlük getiri.** TCD'de 2026-03-20'de -%85, ertesi gün +%680.
      Volatilite, korelasyon, VaR ve TWR bundan doğrudan etkilenir.
    - **Sahte maliyet.** `seed_ledger` alım gününü fiyatı olan günlerden seçer;
      deliğe düşen alım 7 kat ucuza alınmış görünür. Ölçülen: 151 işlem,
      48 portföy (50 kullanıcıdan 48'i).

    KURAL. Gerçek kapsaması yeterli olan varlıkta sentetik satır hiç kalmaz.
    Sentetiğin amacı çevrimdışı çalışabilirlikti (A1); backfill koştuktan sonra
    veritabanının kendisi zaten o deponun yerini alıyor, iç içe duran sentetik
    satır hiçbir şey eklemeden yukarıdaki hataları üretiyor.

    Kapsama yetersizse (yeni eklenmiş varlık, yarım backfill) yalnızca gerçek
    aralığın İÇİNDEKİ delikler silinir; öncesindeki sentetik geçmiş korunur ki
    risk penceresi tamamen boşalmasın.

    Tatil günlerinde fiyatın hiç olmaması doğru davranıştır — piyasa kapalıydı.
    `PriceBook` carry-forward yapıyor, volatilite ortak günlerden hesaplanıyor,
    `seed_ledger` o günü alım için seçemiyor.
    """
    real_ranges = session.execute(
        select(
            PriceHistory.asset_id,
            func.count().label("real_rows"),
            func.min(PriceHistory.price_date).label("first_real"),
            func.max(PriceHistory.price_date).label("last_real"),
        )
        .where(PriceHistory.source != PriceSource.SYNTHETIC)
        .group_by(PriceHistory.asset_id)
    ).all()

    deleted = 0
    for asset_id, real_rows, first_real, last_real in real_ranges:
        condition = (PriceHistory.asset_id == asset_id) & (
            PriceHistory.source == PriceSource.SYNTHETIC
        )
        if real_rows < MIN_REAL_ROWS_FOR_PURE_REAL:
            condition &= PriceHistory.price_date.between(first_real, last_real)
        deleted += session.execute(delete(PriceHistory).where(condition)).rowcount or 0

    return deleted
