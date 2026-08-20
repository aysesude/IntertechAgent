"""Portföy ile ilgili tüm SQL sorguları burada. API katmanı ve MCP tool'ları
bu modülü çağırır, kendileri sorgu yazmaz."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import AssetClass, Granularity, TimeWindow, settings
from app.core.exceptions import InsufficientDataError, NotFoundError, ValidationAppError
from app.models import Asset, Holding, Portfolio, PriceHistory, Transaction, TransactionType
from app.schemas.portfolio import (
    AllocationItem,
    AssetClassReturn,
    BenchmarkComparison,
    BenchmarkEntry,
    GainLoss,
    HoldingRow,
    HoldingsValuation,
    PerformancePoint,
    PerformanceResult,
    PerformanceSummary,
    PerformerRef,
    PeriodChanges,
    PortfolioSummary,
    TransactionList,
    TransactionRow,
)
from app.services.ledger_service import cash_balance_as_of, position_as_of
from app.services.price_service import WINDOW_DAYS, bucket_last, resolve_granularity
from app.services.valuation_service import (
    FX_SYMBOL_BY_CURRENCY,
    PriceBook,
    realized_pnl,
    twr,
    unrealized_pnl,
    value_series,
)

_TWO_DECIMALS = Decimal("0.01")

# Kıyaslama endeksleri. XU100 evrende henüz tanımlı değil; varlık bulunamazsa
# sessizce atlanır, evrene eklendiği gün ek kod olmadan listeye girer.
BENCHMARK_SYMBOLS = ("XU100", "XAUTRY", "USDTRY")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _period_change(series: list[tuple[date, Decimal, Decimal]], days: int) -> Decimal | None:
    """`days` gün önceye göre yüzde değişim; dış akış etkisi ayrıştırılmış.

    ((son_değer − aradaki_dış_akış) / eski_değer − 1) × 100. Yeterli gün veya
    pozitif başlangıç sermayesi yoksa None döner — 0 yazmak "hiç değişmedi"
    demek olurdu ki bu bilgi elimizde yok.
    """
    if len(series) <= days:
        return None
    base_value = series[-1 - days][1]
    if base_value <= 0:
        return None
    flows = sum((point[2] for point in series[-days:]), Decimal(0))
    return _round2(((series[-1][1] - flows) / base_value - 1) * 100)


def _latest_prices(db: Session, asset_ids: list[UUID]) -> dict[UUID, tuple[Decimal, date]]:
    """Verilen varlıklar için en güncel (en son tarihli) kapanış fiyatını döndürür."""
    if not asset_ids:
        return {}

    row_number = (
        func.row_number()
        .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.price_date.desc())
        .label("row_number")
    )
    subquery = (
        select(
            PriceHistory.asset_id,
            PriceHistory.close_price,
            PriceHistory.price_date,
            row_number,
        )
        .where(PriceHistory.asset_id.in_(asset_ids))
        .subquery()
    )
    rows = db.execute(
        select(subquery.c.asset_id, subquery.c.close_price, subquery.c.price_date).where(
            subquery.c.row_number == 1
        )
    ).all()
    return {row.asset_id: (row.close_price, row.price_date) for row in rows}


def _latest_fx_rates(db: Session, currencies: set[str]) -> dict[str, Decimal]:
    """TRY dışı para birimleri için en güncel kuru döndürür (1 birim kaç TRY).

    Kuru bulunamayan para birimi sözlükte HİÇ yer almaz; çağıran taraf bunu
    "değer hesaplanamaz" olarak yorumlar ve 0 ile doldurmaz (AK 5.5).
    """
    fx_symbols = {
        currency: FX_SYMBOL_BY_CURRENCY[currency]
        for currency in currencies
        if currency in FX_SYMBOL_BY_CURRENCY
    }
    if not fx_symbols:
        return {}

    fx_asset_rows = db.execute(
        select(Asset.id, Asset.symbol).where(Asset.symbol.in_(fx_symbols.values()))
    ).all()
    fx_prices = _latest_prices(db, [row.id for row in fx_asset_rows])
    symbol_to_price = {
        row.symbol: fx_prices[row.id][0] for row in fx_asset_rows if row.id in fx_prices
    }
    return {
        currency: symbol_to_price[symbol]
        for currency, symbol in fx_symbols.items()
        if symbol in symbol_to_price
    }


def get_portfolio_summary(db: Session, user_id: UUID) -> PortfolioSummary:
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )

    latest_prices = _latest_prices(db, [h.asset_id for h in holdings])

    # AK 5.7: TRY dışı varlıklar güncel kurla dahil edilir. Kur varlıklarının
    # (USDTRY vb.) son kapanışı price_history'den okunur.
    fx_latest = _latest_fx_rates(
        db, {h.asset.currency for h in holdings if h.asset.currency != "TRY"}
    )

    total_value = Decimal(0)
    total_cost_basis = Decimal(0)
    class_values: dict[AssetClass, Decimal] = {}
    as_of_dates: list[date] = []

    for holding in holdings:
        price, price_date = latest_prices.get(holding.asset_id, (holding.avg_cost_price, None))
        if holding.asset.currency != "TRY":
            fx = fx_latest.get(holding.asset.currency)
            if fx is None:
                # Kur bilinmiyorsa değer uydurulmaz (AK 5.5); varlık toplam
                # değere maliyetiyle değil, hiç katılmaz — maliyet tarafı zaten
                # TRY cinsindendir ve aynen kalır.
                price = None
            else:
                price = price * fx
        market_value = holding.quantity * price if price is not None else Decimal(0)
        # avg_cost_price TRY cinsinden birim maliyettir (işlem anındaki kurla
        # dondurulmuş) — bkz. ledger_service maliyet sözleşmesi.
        cost_basis = holding.quantity * holding.avg_cost_price

        total_value += market_value
        total_cost_basis += cost_basis
        class_values[holding.asset.asset_class] = (
            class_values.get(holding.asset.asset_class, Decimal(0)) + market_value
        )
        if price_date is not None:
            as_of_dates.append(price_date)

    # Serbest nakit (defterden): toplam değere ve 'cash' dilimine eklenir.
    cash_balance = cash_balance_as_of(db, portfolio.id)
    if cash_balance != 0:
        total_value += cash_balance
        class_values[AssetClass.CASH] = class_values.get(AssetClass.CASH, Decimal(0)) + cash_balance

    gain_amount = total_value - total_cost_basis
    gain_percent = (gain_amount / total_cost_basis * 100) if total_cost_basis > 0 else Decimal(0)

    class_order = {asset_class: i for i, asset_class in enumerate(settings.supported_asset_classes)}
    allocation = [
        AllocationItem(
            asset_class=asset_class,
            value=_round2(value),
            percent=_round2(value / total_value * 100) if total_value > 0 else Decimal(0),
        )
        for asset_class, value in sorted(class_values.items(), key=lambda kv: class_order[kv[0]])
    ]

    return PortfolioSummary(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        total_value=_round2(total_value),
        total_cost_basis=_round2(total_cost_basis),
        total_gain_loss=GainLoss(amount=_round2(gain_amount), percent=_round2(gain_percent)),
        allocation=allocation,
        # Tamamen satılmış (quantity=0) satırlar gerçekleşmiş K-Z taşımak için
        # tabloda durur; aktif pozisyon sayısına katılmaz.
        holdings_count=sum(1 for h in holdings if h.quantity > 0),
    )


# ---------------------------------------------------------------------------
# Faz 2'de uygulanacak fonksiyonlar
#
# İmzalar ve dönüş şemaları sabittir: MCP tool'ları bunlara göre yazıldı ve
# ajanın planlayıcısı tool docstring'lerine göre seçim yapıyor. Gövdeler
# yazılana kadar @tool_handler NotImplementedError'ı INTERNAL_ERROR zarfına
# çevirir; sohbet çökmez, "alınamadı" der.
# ---------------------------------------------------------------------------


def get_holdings_valuation(db: Session, user_id: UUID) -> HoldingsValuation:
    """Portföydeki varlıkları tek tek değerler.

    Maliyet: `Holding.avg_cost_price` zaten TRY birim maliyettir (işlem
    anındaki kurla çevrilmiş, alım komisyonu dahil, ağırlıklı ortalama — bkz.
    ledger_service maliyet sözleşmesi). Dolayısıyla
    `cost_basis_try = quantity * avg_cost_price`; defteri yeniden oynatmaya
    gerek yok.

    Güncel fiyat `_latest_prices` ile okunur; TRY dışı varlıklarda
    `get_portfolio_summary`'deki kur çevirimi kalıbı kullanılır. Kuru veya
    fiyatı bulunamayan varlık `price_missing=True` ile döner, değer alanları
    None kalır ve ağırlık hesabına girmez (AK-1.3, AK 5.5).

    `best_performer` / `worst_performer` `unrealized_pnl_percent`'e göre
    seçilir; fiyatı eksik varlıklar sıralamaya alınmaz. Bu değerler burada
    hesaplanır çünkü dil modelinin satırları karşılaştırıp en iyiyi bulması
    hesaplama sayılır ve yasaktır.

    quantity = 0 satırları (tamamen satılmış pozisyonlar) listeye dahil edilir:
    `realized_pnl_try` bilgisini taşırlar.

    AĞIRLIK PAYDASI: nakit DAHİL toplam portföy değeri — yani
    `get_portfolio_summary.total_value` ile aynı payda. Böylece buradaki varlık
    ağırlıkları pasta grafiğindeki sınıf ağırlıklarının içine tutarlı biçimde
    oturur. Sonuç: satırların ağırlıkları 100'e değil, (100 − nakit%) değerine
    toplanır. Nakit bir "holding" satırı olmadığı için burada listelenmez.

    Raises:
        NotFoundError: kullanıcının portföyü yok.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )

    latest_prices = _latest_prices(db, [h.asset_id for h in holdings])
    fx_latest = _latest_fx_rates(
        db, {h.asset.currency for h in holdings if h.asset.currency != "TRY"}
    )

    # İki geçiş gerekiyor: ağırlığın paydası (toplam portföy değeri) ancak tüm
    # satırlar değerlendikten sonra biliniyor.
    ara_satirlar: list[dict] = []
    as_of_dates: list[date] = []
    excluded_symbols: list[str] = []
    total_market_value = Decimal(0)

    for holding in holdings:
        asset = holding.asset
        price, price_date = latest_prices.get(holding.asset_id, (None, None))

        # TRY dışı varlık: O GÜNÜN değil, en güncel kurla çevrilir — bu
        # fonksiyon "şu an ne kadar eder" sorusunu cevaplıyor.
        if price is not None and asset.currency != "TRY":
            fx = fx_latest.get(asset.currency)
            price = None if fx is None else price * fx

        # avg_cost_price TRY birim maliyettir (işlem anındaki kurla dondurulmuş,
        # komisyon dahil) — bkz. ledger_service maliyet sözleşmesi.
        cost_basis = _round2(holding.quantity * holding.avg_cost_price)

        if price is None:
            # Fiyat veya kur yok: satır düşmez ama değer alanları None kalır.
            excluded_symbols.append(asset.symbol)
            market_value = None
            price_try = None
            unrealized = None
            unrealized_percent = None
        else:
            price_try = _round2(price)
            market_value = _round2(holding.quantity * price)
            total_market_value += market_value
            unrealized = _round2(market_value - cost_basis)
            # Maliyeti sıfır olan satırda yüzde tanımsız (tamamen satılmış
            # pozisyon ya da bedelsiz giriş); 0 yazmak yanlış olurdu.
            unrealized_percent = _round2(unrealized / cost_basis * 100) if cost_basis > 0 else None
            if price_date is not None:
                as_of_dates.append(price_date)

        ara_satirlar.append(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_class": asset.asset_class,
                "currency": asset.currency,
                "quantity": holding.quantity,
                "current_price_try": price_try,
                "market_value_try": market_value,
                "avg_cost_try": holding.avg_cost_price,
                "cost_basis_try": cost_basis,
                "unrealized_pnl_try": unrealized,
                "unrealized_pnl_percent": unrealized_percent,
                "realized_pnl_try": _round2(holding.realized_pnl_try),
                "price_missing": price is None,
            }
        )

    # Payda get_portfolio_summary ile aynı olmalı: serbest nakit de dahil.
    total_portfolio_value = total_market_value + cash_balance_as_of(db, portfolio.id)

    # Tablo okunabilirliği: büyükten küçüğe, fiyatı bilinmeyenler en sonda.
    ara_satirlar.sort(
        key=lambda r: (r["market_value_try"] is None, -(r["market_value_try"] or Decimal(0)))
    )

    rows = [
        HoldingRow(
            **satir,
            weight_percent=(
                _round2(satir["market_value_try"] / total_portfolio_value * 100)
                if satir["market_value_try"] is not None and total_portfolio_value > 0
                else None
            ),
        )
        for satir in ara_satirlar
    ]

    # En iyi/en kötü: yüzdesi hesaplanabilen AÇIK pozisyonlar arasından.
    # Kapanmış (quantity=0) satırın güncel getirisi yoktur, sıralamaya girmez.
    ranked = [r for r in rows if r.unrealized_pnl_percent is not None and r.quantity > 0]

    def _performer(row: HoldingRow) -> PerformerRef:
        return PerformerRef(
            symbol=row.symbol,
            name=row.name,
            unrealized_pnl_percent=row.unrealized_pnl_percent,
        )

    return HoldingsValuation(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        holdings=rows,
        best_performer=(
            _performer(max(ranked, key=lambda r: r.unrealized_pnl_percent)) if ranked else None
        ),
        worst_performer=(
            _performer(min(ranked, key=lambda r: r.unrealized_pnl_percent)) if ranked else None
        ),
        excluded_symbols=excluded_symbols,
    )


def get_portfolio_performance(db: Session, user_id: UUID, window: TimeWindow) -> PerformanceResult:
    """Portföyün değer serisini ve dönemsel değişimini üretir.

    `valuation_service.value_series` sarmalanır: o fonksiyon (gün, toplam
    değer, dış akış) üçlüsü döndürüyor. Buradaki iş üç adım:

    1. Dış akışı kümülatife çevir → `invested_try`. Yalnızca DEPOSIT/WITHDRAW
       sayılır (value_series zaten öyle yapıyor); BUY/SELL yeni para değildir,
       sayılırsa sat-yeniden al yapan kullanıcıda tutar şişer.
    2. Seriyi hedef nokta sayısına indir (~60-120). Her kovanın SON işlem günü
       değeri alınır, ortalama ALINMAZ — ortalama hiç var olmamış bir değer
       üretir. Hafta sonları seriye girmez.
    3. Özet skalerleri hesapla. `changes.daily/weekly/monthly` için yeterli
       veri yoksa None döner, 0 değil.

    `start = max(inception, as_of - window)`; pencere portföyün ömründen
    uzunsa `truncated_to_inception=True`. İlk işlemden önce dolgu yapılmaz —
    portföy yokken değeri 0 göstermek uydurma veridir.

    ÖZET ÇİFTİ: `change_amount` ile `change_percent` birlikte okunmalı ve
    ikisi de dış akıştan ARINDIRILMIŞTIR:

    - `change_amount` = (son değer − ilk değer) − dönem içi net para giriş/çıkışı
    - `change_percent` = TWR (zaman ağırlıklı getiri)

    Ham değer farkı kullanılsaydı, para yatıran kullanıcı hiçbir şey kazanmadan
    "kâr ettim" görürdü. Grafikteki `value_try` ↔ `invested_try` boşluğu ise
    ham hâliyle duruyor; kullanıcı toplam kârı oradan görüyor.

    Raises:
        NotFoundError: portföy yok.
        InsufficientDataError: portföyde hiç işlem yok ya da pencerede veri yok.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    inception_dt = db.execute(
        select(func.min(Transaction.transaction_date)).where(
            Transaction.portfolio_id == portfolio.id
        )
    ).scalar()
    if inception_dt is None:
        raise InsufficientDataError(f"No transactions for portfolio {portfolio.id}")
    inception = inception_dt.date()

    # Seri son FİYAT gününde biter, bugünde değil: fiyat hattı geride kalmışsa
    # (daily_update çalışmamışsa) bugüne kadar uzatmak, son bilinen fiyatı
    # tekrar tekrar çizip "değer değişmedi" yanılsaması üretirdi.
    portfolio_asset_ids = (
        db.execute(
            select(Transaction.asset_id)
            .where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.asset_id.is_not(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    last_price_date = db.execute(
        select(func.max(PriceHistory.price_date)).where(
            PriceHistory.asset_id.in_(portfolio_asset_ids)
        )
    ).scalar()
    as_of = last_price_date or date.today()

    window_days = WINDOW_DAYS[window]
    window_start = as_of - timedelta(days=window_days)
    start = max(inception, window_start)
    truncated = inception > window_start
    if start > as_of:
        raise InsufficientDataError(
            f"No data in window for portfolio {portfolio.id} ({start} > {as_of})"
        )

    series = value_series(db, portfolio.id, start, as_of)
    if not series:
        raise InsufficientDataError(f"Empty value series for portfolio {portfolio.id}")

    # Kümülatif yatırılan para pencerenin başında sıfırlanmaz: grafikteki
    # "değer ↔ yatırılan" boşluğu ancak portföyün başından beri sayıldığında
    # toplam kârı gösterir.
    flow_before_start = db.execute(
        select(func.coalesce(func.sum(Transaction.cash_amount_try), 0)).where(
            Transaction.portfolio_id == portfolio.id,
            Transaction.transaction_type.in_([TransactionType.DEPOSIT, TransactionType.WITHDRAW]),
            func.date(Transaction.transaction_date) < start,
        )
    ).scalar() or Decimal(0)

    cumulative: dict[date, Decimal] = {}
    running = Decimal(flow_before_start)
    for day, _value, flow in series:
        running += flow
        cumulative[day] = running

    # Hafta sonları düşer: borsa kapalı, fiyat taşındığı için o günler grafikte
    # yatay tekrar üretir. Akış birikimi yukarıda TÜM günler üzerinden
    # yapıldığı için hafta sonu yatırılan para kaybolmaz.
    weekdays = [point for point in series if point[0].weekday() < 5]
    if not weekdays:
        weekdays = series

    granularity = resolve_granularity(window, Granularity.AUTO)
    points = [
        PerformancePoint(date=day, value_try=value, invested_try=cumulative[day])
        for day, value, _flow in bucket_last(weekdays, granularity)
    ]

    start_value = series[0][1]
    end_value = series[-1][1]
    # İlk günün akışı başlangıç sermayesidir, dönem içi giriş sayılmaz.
    net_flow = sum((point[2] for point in series[1:]), Decimal(0))

    summary = PerformanceSummary(
        start_value=start_value,
        end_value=end_value,
        change_amount=_round2(end_value - start_value - net_flow),
        change_percent=twr(db, portfolio.id, start, as_of),
        realized_pnl=realized_pnl(db, portfolio.id, start, as_of),
        unrealized_pnl=unrealized_pnl(db, portfolio.id, as_of),
        changes=PeriodChanges(
            daily=_period_change(series, 1),
            weekly=_period_change(series, 7),
            monthly=_period_change(series, 30),
        ),
    )

    return PerformanceResult(
        user_id=user_id,
        as_of=as_of,
        window=window,
        granularity=granularity,
        inception=inception,
        truncated_to_inception=truncated,
        series=points,
        summary=summary,
    )


def get_transactions(
    db: Session,
    user_id: UUID,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    symbols: list[str] | None = None,
) -> TransactionList:
    """İşlem defterini filtreleyerek döndürür.

    `position_after` defterin tarih sırasıyla oynatılmasıyla üretilir:
    grafikteki alım işaretçisinin hover detayında "bu işlemden sonra elimde ne
    kaldı" bilgisi için. Filtre uygulansa bile pozisyon defterin başından
    itibaren sayılmalıdır, yoksa değer yanlış çıkar.

    `symbols` verilmezse nakit hareketleri (DEPOSIT/WITHDRAW/FEE/INTEREST) de
    listeye girer; verilirse yalnızca o sembollere ait BUY/SELL/DIVIDEND döner.

    SIRALAMA: eskiden yeniye. Grafikteki işaretçiler zaman ekseninde soldan
    sağa diziliyor; `position_after` da ancak bu sırada anlamlı.

    Raises:
        NotFoundError: portföy yok.
        ValidationAppError: start_date > end_date.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValidationAppError(f"start_date {start_date} is after end_date {end_date}")

    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    # Defterin TAMAMI okunur, filtre sonradan uygulanır: `position_after`
    # "bu işlemden sonra elimde ne kaldı" demek ve bu ancak baştan sayılarak
    # bulunur. Yalnızca filtrelenmiş aralık oynatılsaydı, pencere öncesindeki
    # alımlar sayılmaz ve pozisyon olduğundan küçük çıkardı.
    transactions = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio.id)
            .options(joinedload(Transaction.asset))
            .order_by(Transaction.transaction_date, Transaction.created_at)
        )
        .scalars()
        .all()
    )

    wanted_symbols = {s.strip().upper() for s in symbols} if symbols else None

    running: dict[UUID, Decimal] = {}
    rows: list[TransactionRow] = []

    for tx in transactions:
        # Pozisyon her işlemde güncellenir — satır filtreye takılsa bile,
        # yoksa sayaç bozulur.
        position_after: Decimal | None = None
        if tx.asset_id is not None:
            quantity = running.get(tx.asset_id, Decimal(0))
            if tx.transaction_type == TransactionType.BUY:
                quantity += tx.quantity
            elif tx.transaction_type == TransactionType.SELL:
                quantity -= tx.quantity
            # DIVIDEND miktarı değiştirmez, yalnızca nakit getirir.
            running[tx.asset_id] = quantity
            position_after = quantity

        tx_date = tx.transaction_date.date()
        if start_date is not None and tx_date < start_date:
            continue
        if end_date is not None and tx_date > end_date:
            continue

        symbol = tx.asset.symbol if tx.asset is not None else None
        if wanted_symbols is not None:
            # Sembol süzgeci verildiğinde nakit hareketleri (DEPOSIT/WITHDRAW/
            # FEE/INTEREST) listeye girmez: "TUPRS'ta ne yaptım" sorusunun
            # cevabında maaş yatırma kaydının işi yok.
            if symbol is None or symbol not in wanted_symbols:
                continue

        rows.append(
            TransactionRow(
                transaction_date=tx.transaction_date,
                type=tx.transaction_type,
                symbol=symbol,
                quantity=tx.quantity,
                price=tx.price,
                currency=tx.currency,
                fx_rate_to_try=tx.fx_rate_to_try,
                fee_try=_round2(tx.fee_try),
                cash_amount_try=_round2(tx.cash_amount_try),
                position_after=position_after,
            )
        )

    return TransactionList(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        transactions=rows,
    )


def get_benchmark_comparison(db: Session, user_id: UUID, window: TimeWindow) -> BenchmarkComparison:
    """Portföyün dönem getirisini endekslerle karşılaştırır.

    METRİK — pencere başındaki (t0) miktarlar SABİT tutulur, yalnızca fiyat
    değişimi ölçülür:

        C = Σ qᵢ(t0) × pᵢ(t0)        V = Σ qᵢ(t0) × pᵢ(t1)
        getiri% = 100 × (V / C − 1)

    Pencere içindeki alım/satım, temettü ve komisyon hesaba KATILMAZ; endeksin
    saf fiyat getirisiyle aynı ölçekte olması için. Miktarlar t0'da donduğu ve
    fiyatlar pozitif olduğu için C > 0 garantidir — negatif payda sorunu yok.

    `qᵢ(t0)` için `ledger_service.position_as_of`, fiyatlar için
    `valuation_service` kur çevirimi kullanılır (bugünkü kur değil, O GÜNÜN
    kuru).

    Varlık sınıfı kırılımı aynı formülün o sınıfa kısıtlanmış hâlidir;
    ağırlıklı ortalama almaya gerek yok, ΣV/ΣC zaten ağırlıklı ortalamadır.

    `t0` fiyatı bulunmayan varlık dışlanır ve `excluded_symbols` ile bildirilir.
    Benchmark'lar XU100, XAUTRY, USDTRY — aynı pencerede
    100 × (p(t1)/p(t0) − 1).

    XU100 evrende (`app/providers/universe.py`) HENÜZ TANIMLI DEĞİL. Sembol
    `BENCHMARK_SYMBOLS` içinde duruyor ama varlık bulunamazsa listeye hiç
    girmiyor — boş bir "BIST100: —" satırı göstermek, veri varmış da
    hesaplanamamış gibi okunurdu. Evrene eklendiği gün (provider_symbol
    "XU100.IS") bu fonksiyon değişmeden çalışmaya başlar.

    Raises:
        NotFoundError: portföy yok.
        InsufficientDataError: hiç işlem yok ya da t0'da hiç pozisyon yok.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    inception_dt = db.execute(
        select(func.min(Transaction.transaction_date)).where(
            Transaction.portfolio_id == portfolio.id
        )
    ).scalar()
    if inception_dt is None:
        raise InsufficientDataError(f"No transactions for portfolio {portfolio.id}")
    inception = inception_dt.date()

    portfolio_asset_ids = (
        db.execute(
            select(Transaction.asset_id)
            .where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.asset_id.is_not(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    last_price_date = db.execute(
        select(func.max(PriceHistory.price_date)).where(
            PriceHistory.asset_id.in_(portfolio_asset_ids)
        )
    ).scalar()
    end_date = last_price_date or date.today()

    window_start = end_date - timedelta(days=WINDOW_DAYS[window])
    start_date = max(inception, window_start)
    truncated = inception > window_start

    # t0'daki miktarlar DONDURULUR: pencere içindeki alım/satım, temettü ve
    # komisyon hesaba katılmaz. Endeks de saf fiyat getirisi olduğu için ancak
    # böyle aynı ölçekte olurlar (yoksa "portföyüm endeksi yendi" cümlesi,
    # aslında sadece yeni para yatırıldığı anlamına gelirdi).
    positions = position_as_of(db, portfolio.id, start_date)
    if not positions:
        raise InsufficientDataError(f"No positions at {start_date} for portfolio {portfolio.id}")

    benchmark_assets = (
        db.execute(select(Asset).where(Asset.symbol.in_(BENCHMARK_SYMBOLS))).scalars().all()
    )
    position_assets = db.execute(select(Asset).where(Asset.id.in_(list(positions)))).scalars().all()

    # Kur varlıkları da fiyat defterine girmeli: TRY dışı varlık O GÜNÜN
    # kuruyla çevrilir, bugünkü kurla değil.
    currencies = {a.currency for a in position_assets if a.currency != "TRY"}
    fx_rows = db.execute(
        select(Asset.id, Asset.symbol).where(
            Asset.symbol.in_(
                [FX_SYMBOL_BY_CURRENCY[c] for c in currencies if c in FX_SYMBOL_BY_CURRENCY]
            )
        )
    ).all()
    fx_id_by_symbol = {symbol: asset_id for asset_id, symbol in fx_rows}
    fx_id_by_currency = {
        currency: fx_id_by_symbol[FX_SYMBOL_BY_CURRENCY[currency]]
        for currency in currencies
        if FX_SYMBOL_BY_CURRENCY.get(currency) in fx_id_by_symbol
    }

    book_asset_ids = (
        set(positions) | {a.id for a in benchmark_assets} | set(fx_id_by_currency.values())
    )
    price_rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price).where(
            PriceHistory.asset_id.in_(list(book_asset_ids))
        )
    ).all()
    book = PriceBook([(r.asset_id, r.price_date, r.close_price) for r in price_rows])

    currency_by_asset = {a.id: a.currency for a in position_assets}

    def _price_try(asset_id: UUID, day: date) -> Decimal | None:
        """Varlığın o günkü TRY fiyatı. Kur veya fiyat yoksa None — eksik veri
        tamamlanmaz (AK 5.5)."""
        price = book.price_at(asset_id, day)
        if price is None:
            return None
        currency = currency_by_asset.get(asset_id, "TRY")
        if currency == "TRY":
            return price
        fx_asset_id = fx_id_by_currency.get(currency)
        if fx_asset_id is None:
            return None
        fx = book.price_at(fx_asset_id, day)
        return None if fx is None else price * fx

    asset_by_id = {a.id: a for a in position_assets}
    total_cost = Decimal(0)
    total_value = Decimal(0)
    by_class: dict[AssetClass, list[Decimal]] = {}
    excluded_symbols: list[str] = []

    for asset_id, quantity in positions.items():
        asset = asset_by_id.get(asset_id)
        if asset is None:
            continue
        price_start = _price_try(asset_id, start_date)
        price_end = _price_try(asset_id, end_date)
        if price_start is None or price_end is None or price_start <= 0:
            # Pencere başında fiyatı olmayan varlık dışlanır: eksik maliyetle
            # bölmek yanlış getiri üretir.
            excluded_symbols.append(asset.symbol)
            continue
        cost = quantity * price_start
        value = quantity * price_end
        total_cost += cost
        total_value += value
        bucket = by_class.setdefault(asset.asset_class, [Decimal(0), Decimal(0)])
        bucket[0] += cost
        bucket[1] += value

    def _return_percent(cost: Decimal, value: Decimal) -> Decimal | None:
        return _round2((value / cost - 1) * 100) if cost > 0 else None

    class_order = {asset_class: i for i, asset_class in enumerate(settings.supported_asset_classes)}
    by_asset_class = [
        AssetClassReturn(asset_class=asset_class, return_percent=_return_percent(*sums))
        for asset_class, sums in sorted(by_class.items(), key=lambda kv: class_order[kv[0]])
    ]

    # Endeksler aynı pencerede saf fiyat getirisi: 100 × (p(t1)/p(t0) − 1).
    # Sıra BENCHMARK_SYMBOLS'e sadık kalır ki arayüzdeki bar grafiği her
    # çağrıda aynı düzende çizilsin.
    benchmark_by_symbol = {a.symbol: a for a in benchmark_assets}
    benchmarks: list[BenchmarkEntry] = []
    for symbol in BENCHMARK_SYMBOLS:
        asset = benchmark_by_symbol.get(symbol)
        if asset is None:
            continue
        price_start = book.price_at(asset.id, start_date)
        price_end = book.price_at(asset.id, end_date)
        benchmarks.append(
            BenchmarkEntry(
                symbol=asset.symbol,
                name=asset.name,
                return_percent=(
                    _round2((price_end / price_start - 1) * 100)
                    if price_start and price_end and price_start > 0
                    else None
                ),
            )
        )

    return BenchmarkComparison(
        user_id=user_id,
        window=window,
        start_date=start_date,
        end_date=end_date,
        truncated_to_inception=truncated,
        portfolio_return_percent=_return_percent(total_cost, total_value),
        by_asset_class=by_asset_class,
        benchmarks=benchmarks,
        excluded_symbols=excluded_symbols,
    )
