"""Fiyat serisi servisi: portföyden bağımsız piyasa verisi.

Bu katman **veritabanını okur, internete çıkmaz.** Fiyatların tazeliği yazma
hattının sorumluluğudur (`app/services/price_ingest.py`, `make daily-update`).
Ayrımın sebepleri:

- Sağlayıcı çöktüğünde sohbet çalışmaya devam eder; son bilinen veri kullanılır
  (AK-6.10). Tool canlı çekseydi sağlayıcı kesintisi sohbet kesintisi olurdu.
- Tool zaman aşımı 10 sn; yfinance/TCMB çağrısı tek başına bunu yiyebilir.
- Rapordaki tüm bölümler tek anlık görüntüden üretilmeli (AK-1.7); canlı çekim
  bölümler arasında farklı anlara ait fiyat doğururdu.
- Her fiyat kaydı kaynağı ve çekilme zamanıyla saklanmalı (AK 5.3); tool
  içinden yapılan çağrı `data_ingest_log`'u atlardı.
- "Gerçek kayıt sentetiği ezer, tersi asla" kuralı `upsert_prices` içinde
  yaşıyor; doğrudan çekim onu devre dışı bırakırdı.

Aynı sembolün serisi tüm kullanıcılar için aynı olduğundan bu katman
kullanıcıdan bağımsız önbelleğe uygundur (henüz eklenmedi).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Granularity, PriceCurrency, TimeWindow
from app.core.exceptions import InsufficientDataError, NotFoundError, ValidationAppError
from app.models import Asset, PriceHistory
from app.schemas.portfolio import PriceHistoryResult, PricePoint
from app.services.valuation_service import FX_SYMBOL_BY_CURRENCY, PriceBook

# Grafik hedefi: 700px genişlikte 365 nokta çizmek bilgi değil gürültü, ve seri
# LLM'e giderse ücretli token. AUTO çözünürlük bu aralığı hedefler.
TARGET_POINT_MIN = 60
TARGET_POINT_MAX = 120

# Pencere -> gün sayısı. AUTO çözünürlük seçimi buradan türer: 30/90/180 gün
# günlük (~22/65/130 nokta), 365 gün haftalık (~52 nokta).
WINDOW_DAYS: dict[TimeWindow, int] = {
    TimeWindow.M1: 30,
    TimeWindow.M3: 90,
    TimeWindow.M6: 180,
    TimeWindow.M12: 365,
}

_TWO_DECIMALS = Decimal("0.01")


def resolve_granularity(window: TimeWindow, granularity: Granularity) -> Granularity:
    """AUTO çözünürlüğü pencereye göre somutlaştırır.

    AUTO dışındaki değerler olduğu gibi döner: risk tarafı DAILY istemek
    zorundadır (volatilite günlük getirilerden hesaplanır; haftalık seriden
    hesaplanan volatilite yanlış ölçekte çıkar), bu yüzden çağıranın açık
    seçimi ezilmez.
    """
    if granularity is not Granularity.AUTO:
        return granularity
    return Granularity.WEEKLY if window is TimeWindow.M12 else Granularity.DAILY


def bucket_key(day: date, granularity: Granularity):
    """Günün hangi indirgeme kovasına düştüğü."""
    if granularity is Granularity.WEEKLY:
        iso = day.isocalendar()
        return (iso[0], iso[1])
    if granularity is Granularity.MONTHLY:
        return (day.year, day.month)
    return day


def bucket_last(points: list[tuple], granularity: Granularity) -> list[tuple]:
    """Her kovanın SON gününü alır (ilk eleman tarih olan tuple listesi).

    Ortalama ALINMAZ: ortalama, fiyatın hiçbir gün almadığı bir değer üretir ve
    grafikteki son nokta ile özet skalerleri birbirini tutmaz. Kovanın son günü
    gerçekten var olmuş bir değerdir.

    Burada duruyor çünkü hem fiyat serisi hem portföy değer serisi aynı
    indirgemeyi kullanıyor; iki kopya olsa biri düzeltilip diğeri unutulurdu.
    """
    if granularity is Granularity.DAILY:
        return points
    seen: dict = {}
    for point in points:
        seen[bucket_key(point[0], granularity)] = point
    return list(seen.values())


def get_asset_price_history(
    db: Session,
    symbols: list[str],
    *,
    window: TimeWindow = TimeWindow.M3,
    granularity: Granularity = Granularity.AUTO,
    currency: PriceCurrency = PriceCurrency.TRY,
) -> PriceHistoryResult:
    """Sembollerin geçmiş kapanış serisini `price_history` tablosundan döndürür.

    KISMİ VERİ HATA DEĞİLDİR. İstenen pencerenin tamamı veritabanında yoksa
    eldeki kadarı döner ve `actual_start` gerçek başlangıcı bildirir. Bir
    sembolün verisinin olmaması diğerlerinin serisini engellemez; o sembol
    `symbols_without_data` ile raporlanır. Hepsi birden boşsa
    `InsufficientDataError` fırlar (ör. `make backfill` hiç çalıştırılmamış).

    Kova indirgemesinde o kovanın SON işlem günü değeri alınır; ortalama
    ALINMAZ — ortalama hiç var olmamış bir fiyat üretir. Hafta sonları seride
    yer almaz (fiyatlar yalnızca hafta içi üretiliyor; carry-forward tekrarı
    grafikte anlamsız düz basamak yaratır).

    TRY para biriminde O GÜNÜN kuru kullanılır — bugünkü kurla geçmişi
    çevirmek tarihsel değeri bozar (`valuation_service._price_try` aynı kuralı
    uyguluyor, kalıbı oradan alınabilir). NATIVE'de çevirim yapılmaz.

    Türetilmiş varlıklar (çeyrek altın, yarım altın vb.) kendi `price_history`
    satırlarına sahip olduğu için ek çözümleme gerekmez (bkz. `price_ingest`).

    Args:
        db: Veritabanı oturumu.
        symbols: Sembol listesi. Boş olamaz.
        window: Pencere; başlangıç `as_of - WINDOW_DAYS[window]`.
        granularity: AUTO ise `resolve_granularity` ile somutlaşır.
        currency: TRY (o günün kuruyla çevrilmiş) veya NATIVE.

    Raises:
        ValidationAppError: sembol listesi boş.
        NotFoundError: hiçbir sembol varlık evreninde tanınmadı.
        InsufficientDataError: semboller tanındı ama hiçbirinin bu pencerede
            fiyat kaydı yok.
    """
    if not symbols:
        raise ValidationAppError("symbols must not be empty")

    requested = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
    if not requested:
        raise ValidationAppError("symbols must not be empty")

    assets = db.execute(select(Asset).where(Asset.symbol.in_(requested))).scalars().all()
    if not assets:
        raise NotFoundError(f"No known assets among {requested}")

    asset_by_symbol = {asset.symbol: asset for asset in assets}
    # Sıra kullanıcının istediği gibi korunur; tekrarlar elenir.
    known_symbols = list(dict.fromkeys(s for s in requested if s in asset_by_symbol))
    unknown_symbols = [s for s in dict.fromkeys(requested) if s not in asset_by_symbol]

    # TRY'ye çevrim O GÜNÜN kuruyla yapılır; kur varlıkları da deftere girmeli.
    fx_id_by_currency: dict[str, object] = {}
    if currency is PriceCurrency.TRY:
        currencies = {a.currency for a in assets if a.currency != "TRY"}
        fx_symbols = [FX_SYMBOL_BY_CURRENCY[c] for c in currencies if c in FX_SYMBOL_BY_CURRENCY]
        if fx_symbols:
            fx_rows = db.execute(
                select(Asset.id, Asset.symbol).where(Asset.symbol.in_(fx_symbols))
            ).all()
            fx_id_by_symbol = {symbol: asset_id for asset_id, symbol in fx_rows}
            fx_id_by_currency = {
                c: fx_id_by_symbol[FX_SYMBOL_BY_CURRENCY[c]]
                for c in currencies
                if FX_SYMBOL_BY_CURRENCY.get(c) in fx_id_by_symbol
            }

    asset_ids = [a.id for a in assets]
    as_of = db.execute(
        select(func.max(PriceHistory.price_date)).where(PriceHistory.asset_id.in_(asset_ids))
    ).scalar()
    if as_of is None:
        raise InsufficientDataError(f"No price history for {known_symbols}")

    effective_granularity = resolve_granularity(window, granularity)
    requested_start = as_of - timedelta(days=WINDOW_DAYS[window])

    # Kur serisi pencerenin tamamını kapsamalı; ayrı bir aralık sorgusu yerine
    # tek seferde okunup PriceBook'un carry-forward'ına bırakılıyor.
    book_ids = set(asset_ids) | set(fx_id_by_currency.values())
    rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price).where(
            PriceHistory.asset_id.in_(list(book_ids))
        )
    ).all()
    book = PriceBook([(r.asset_id, r.price_date, r.close_price) for r in rows])

    days_by_asset: dict[object, list[date]] = {}
    for row in rows:
        if requested_start <= row.price_date <= as_of:
            days_by_asset.setdefault(row.asset_id, []).append(row.price_date)

    series: dict[str, list[PricePoint]] = {}
    symbols_without_data: list[str] = []
    actual_start: date | None = None

    for symbol in known_symbols:
        asset = asset_by_symbol[symbol]
        # Hafta sonları düşer: fiyat yalnızca hafta içi üretiliyor, carry-forward
        # tekrarı grafikte anlamsız düz basamak yaratır.
        days = sorted({d for d in days_by_asset.get(asset.id, []) if d.weekday() < 5})
        if not days:
            symbols_without_data.append(symbol)
            continue

        fx_asset_id = (
            fx_id_by_currency.get(asset.currency)
            if currency is PriceCurrency.TRY and asset.currency != "TRY"
            else None
        )
        needs_fx = currency is PriceCurrency.TRY and asset.currency != "TRY"
        if needs_fx and fx_asset_id is None:
            # Kur bilinmiyorsa seri uydurulmaz (AK 5.5).
            symbols_without_data.append(symbol)
            continue

        points: list[tuple[date, Decimal]] = []
        for day in days:
            close = book.price_at(asset.id, day)
            if close is None:
                continue
            if needs_fx:
                fx = book.price_at(fx_asset_id, day)
                if fx is None:
                    continue
                close = close * fx
            points.append((day, close.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)))

        if not points:
            symbols_without_data.append(symbol)
            continue

        reduced = bucket_last(points, effective_granularity)
        series[symbol] = [PricePoint(date=day, close=close) for day, close in reduced]
        first_day = reduced[0][0]
        actual_start = first_day if actual_start is None else min(actual_start, first_day)

    if not series:
        raise InsufficientDataError(
            f"No price data in window for {known_symbols} (since {requested_start})"
        )

    return PriceHistoryResult(
        as_of=as_of,
        window=window,
        granularity=effective_granularity,
        currency=currency,
        requested_start=requested_start,
        actual_start=actual_start,
        series=series,
        unknown_symbols=unknown_symbols,
        symbols_without_data=symbols_without_data,
    )
