"""Portföy değerleme: değer serisi, TWR, gerçekleşmiş/gerçekleşmemiş K-Z.

Kur dönüşümü (AK 5.7) BURADA yapılır: `assets.currency != 'TRY'` olan varlığın
değeri, İLGİLİ GÜNÜN kur kapanışıyla TRY'ye çevrilir (bugünkü kurla değil —
tarihsel seride bugünün kuru geçmişi çarpıtır). Kur serileri zaten
price_history'dedir (USDTRY, EURTRY, ...).

Getiri metodolojisi: grafikte TWR (zaman ağırlıklı getiri). DEPOSIT/WITHDRAW
dış akıştır; TWR bunları performanstan ayrıştırır — 100.000 TL yatıran
kullanıcının değer artışı "getiri" değildir (FR-3).
"""

import uuid
from bisect import bisect_right
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, PriceHistory, Transaction, TransactionType
from app.services.ledger_service import replay_transactions

_TWO_DECIMALS = Decimal("0.01")
_ZERO = Decimal(0)

# Varlık para birimi -> TRY kur varlığının kanonik sembolü.
FX_SYMBOL_BY_CURRENCY = {"USD": "USDTRY", "EUR": "EURTRY", "GBP": "GBPTRY", "CHF": "CHFTRY"}


class PriceBook:
    """Varlık başına (tarih -> fiyat) + carry-forward arama: istenen günde
    fiyat yoksa önceki en yakın günün fiyatı kullanılır (son bilinen değer —
    zarif düşüşün okuma tarafı)."""

    def __init__(self, rows: list[tuple[uuid.UUID, date, Decimal]]):
        self._by_asset: dict[uuid.UUID, tuple[list[date], list[Decimal]]] = {}
        buckets: dict[uuid.UUID, list[tuple[date, Decimal]]] = {}
        for asset_id, price_date, close_price in rows:
            buckets.setdefault(asset_id, []).append((price_date, close_price))
        for asset_id, pairs in buckets.items():
            pairs.sort()
            self._by_asset[asset_id] = (
                [d for d, _ in pairs],
                [p for _, p in pairs],
            )

    def price_at(self, asset_id: uuid.UUID, day: date) -> Decimal | None:
        entry = self._by_asset.get(asset_id)
        if entry is None:
            return None
        dates, prices = entry
        index = bisect_right(dates, day)
        return prices[index - 1] if index else None


def _load_price_book(db: Session, asset_ids: set[uuid.UUID]) -> PriceBook:
    if not asset_ids:
        return PriceBook([])
    rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price).where(
            PriceHistory.asset_id.in_(asset_ids)
        )
    ).all()
    return PriceBook([(r.asset_id, r.price_date, r.close_price) for r in rows])


def _load_context(db: Session, portfolio_id: uuid.UUID):
    """İşlemler + ilgili varlıklar + (kur varlıkları dahil) fiyat defteri."""
    transactions = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.transaction_date, Transaction.created_at)
        )
        .scalars()
        .all()
    )
    asset_ids = {tx.asset_id for tx in transactions if tx.asset_id is not None}

    assets = (
        db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars().all()
        if asset_ids
        else []
    )
    currencies = {a.currency for a in assets if a.currency != "TRY"}
    fx_ids: dict[str, uuid.UUID] = {}
    if currencies:
        fx_symbols = [FX_SYMBOL_BY_CURRENCY[c] for c in currencies if c in FX_SYMBOL_BY_CURRENCY]
        fx_rows = db.execute(
            select(Asset.id, Asset.symbol).where(Asset.symbol.in_(fx_symbols))
        ).all()
        symbol_to_id = {symbol: asset_id for asset_id, symbol in fx_rows}
        for currency in currencies:
            symbol = FX_SYMBOL_BY_CURRENCY.get(currency)
            if symbol in symbol_to_id:
                fx_ids[currency] = symbol_to_id[symbol]

    book = _load_price_book(db, asset_ids | set(fx_ids.values()))
    currency_by_asset = {a.id: a.currency for a in assets}
    return transactions, currency_by_asset, fx_ids, book


def _price_try(
    book: PriceBook,
    currency_by_asset: dict,
    fx_ids: dict,
    asset_id: uuid.UUID,
    day: date,
) -> Decimal | None:
    """Varlığın o günkü TRY fiyatı (o günün kuruyla). Kur bilinmiyorsa None —
    eksik veri varsayılarak tamamlanmaz (AK 5.5)."""
    price = book.price_at(asset_id, day)
    if price is None:
        return None
    currency = currency_by_asset.get(asset_id, "TRY")
    if currency == "TRY":
        return price
    fx_asset = fx_ids.get(currency)
    if fx_asset is None:
        return None
    fx = book.price_at(fx_asset, day)
    return None if fx is None else price * fx


def value_series(
    db: Session, portfolio_id: uuid.UUID, start: date, end: date
) -> list[tuple[date, Decimal, Decimal]]:
    """Günlük (gün, toplam değer TRY, o günün dış akışı TRY) serisi.

    Toplam değer = varlıkların TRY değeri + nakit bakiyesi. Fiyatı hiç
    başlamamış varlık o gün 0 katkı verir (yanlış pozitif üretmemek için)."""
    transactions, currency_by_asset, fx_ids, book = _load_context(db, portfolio_id)

    quantities: dict[uuid.UUID, Decimal] = {}
    cash = _ZERO
    flows_by_day: dict[date, Decimal] = {}
    tx_index = 0

    # Aralık öncesi işlemleri uygula (başlangıç pozisyonu).
    while tx_index < len(transactions) and transactions[tx_index].transaction_date.date() < start:
        tx = transactions[tx_index]
        _apply_tx(tx, quantities)
        cash += tx.cash_amount_try
        tx_index += 1

    series: list[tuple[date, Decimal, Decimal]] = []
    day = start
    while day <= end:
        while (
            tx_index < len(transactions) and transactions[tx_index].transaction_date.date() == day
        ):
            tx = transactions[tx_index]
            _apply_tx(tx, quantities)
            cash += tx.cash_amount_try
            if tx.transaction_type in (TransactionType.DEPOSIT, TransactionType.WITHDRAW):
                flows_by_day[day] = flows_by_day.get(day, _ZERO) + tx.cash_amount_try
            tx_index += 1

        total = cash
        for asset_id, quantity in quantities.items():
            if quantity == 0:
                continue
            price_try = _price_try(book, currency_by_asset, fx_ids, asset_id, day)
            if price_try is not None:
                total += quantity * price_try
        series.append(
            (
                day,
                total.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP),
                flows_by_day.get(day, _ZERO),
            )
        )
        day += timedelta(days=1)
    return series


def _apply_tx(tx: Transaction, quantities: dict) -> None:
    if tx.asset_id is None:
        return
    current = quantities.get(tx.asset_id, _ZERO)
    if tx.transaction_type == TransactionType.BUY:
        quantities[tx.asset_id] = current + tx.quantity
    elif tx.transaction_type == TransactionType.SELL:
        quantities[tx.asset_id] = current - tx.quantity


def twr(db: Session, portfolio_id: uuid.UUID, start: date, end: date) -> Decimal | None:
    """Zaman ağırlıklı getiri (%): dış akışların etkisi ayrıştırılmış getiri.

    Günlük alt dönemler üzerinden: r_g = (V_g - F_g) / V_(g-1); TWR = Π(1+r) - 1.
    Aralıkta hiç sermaye yoksa None (getiri tanımsız — uydurulmaz)."""
    series = value_series(db, portfolio_id, start, end)
    if len(series) < 2:
        return None

    growth = Decimal(1)
    had_capital = False
    for i in range(1, len(series)):
        _, value_prev, _ = series[i - 1]
        _, value_now, flow_now = series[i]
        if value_prev <= 0:
            continue  # sermaye yokken getiri tanımsız; gün atlanır
        had_capital = True
        growth *= (value_now - flow_now) / value_prev
    if not had_capital:
        return None
    return ((growth - 1) * 100).quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def realized_pnl(
    db: Session, portfolio_id: uuid.UUID, start: date | None = None, end: date | None = None
) -> Decimal:
    """Gerçekleşmiş K-Z (TRY): satış/temettüyle kilitlenen kazanç. Aralık
    verilirse dönemsel fark alınır (defter tekrarı ile — I1 ile aynı mantık)."""
    transactions = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.transaction_date, Transaction.created_at)
        )
        .scalars()
        .all()
    )

    def realized_until(day: date | None) -> Decimal:
        subset = (
            transactions
            if day is None
            else [tx for tx in transactions if tx.transaction_date.date() <= day]
        )
        return sum(
            (state.realized_pnl_try for state in replay_transactions(subset).values()), _ZERO
        )

    total = realized_until(end)
    if start is not None:
        total -= realized_until(start - timedelta(days=1))
    return total.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def unrealized_pnl(db: Session, portfolio_id: uuid.UUID, as_of: date | None = None) -> Decimal:
    """Gerçekleşmemiş K-Z (TRY): eldeki pozisyonların o günkü değeri - maliyeti."""
    transactions, currency_by_asset, fx_ids, book = _load_context(db, portfolio_id)
    if as_of is None:
        as_of = date.today()
    subset = [tx for tx in transactions if tx.transaction_date.date() <= as_of]
    states = replay_transactions(subset)

    total = _ZERO
    for asset_id, state in states.items():
        if state.quantity == 0:
            continue
        price_try = _price_try(book, currency_by_asset, fx_ids, asset_id, as_of)
        if price_try is None:
            continue  # fiyatı bilinmeyen varlık için K-Z uydurulmaz (AK 5.5)
        total += state.quantity * price_try - state.quantity * state.avg_cost_try
    return total.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)
