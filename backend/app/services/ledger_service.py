"""İşlem defteri servisi — defterin TEK yazma kapısı ve defterden türetilen
tüm pozisyon/nakit sorguları.

Kurallar:
- `transactions` append-only'dir; düzeltme ters kayıtla yapılır. UPDATE/DELETE
  bu modülde bilerek yoktur.
- `holdings` önbellektir; yalnızca `rebuild_holdings` yazar. Elle holdings
  yazan kod, mutabakat testini (I1) kırar ve yanlıştır.
- Nakit bakiyesi hiçbir anda negatife düşemez (I2); `record_transaction`
  yazmadan önce kontrol eder.

Maliyet sözleşmesi: `avg_cost_price` TRY cinsinden birim maliyettir (işlem
anındaki kurla çevrilmiş, alım komisyonu dahil). Ağırlıklı ortalama yöntemi
kullanılır (FIFO/LIFO lot takibi kapsam dışı).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Holding, Transaction, TransactionType

_COST_QUANT = Decimal("0.000001")
_TRY_QUANT = Decimal("0.0001")
_ZERO = Decimal(0)

# Nakit ayağı negatif (para çıkar) olan işlem tipleri; kalanlar pozitif.
_OUTFLOW_TYPES = {TransactionType.BUY, TransactionType.WITHDRAW, TransactionType.FEE}
_ASSET_REQUIRED_TYPES = {TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND}


class LedgerError(ValueError):
    """Defter kuralını ihlal eden yazma denemesi (ör. yetersiz nakit)."""


def cash_balance_as_of(db: Session, portfolio_id: uuid.UUID, day: date | None = None) -> Decimal:
    """Nakit bakiyesi = SUM(cash_amount_try). Defter dengeli olduğu sürece
    ayrı bir bakiye kolonuna gerek yoktur (bkz. DB planı §5)."""
    query = select(func.coalesce(func.sum(Transaction.cash_amount_try), 0)).where(
        Transaction.portfolio_id == portfolio_id
    )
    if day is not None:
        query = query.where(func.date(Transaction.transaction_date) <= day)
    # SQLite toplamı float döndürebilir; str üzerinden Decimal'e alınır.
    return Decimal(str(db.execute(query).scalar_one()))


def record_transaction(
    db: Session,
    portfolio_id: uuid.UUID,
    transaction_type: TransactionType,
    *,
    transaction_date: datetime,
    asset_id: uuid.UUID | None = None,
    quantity: Decimal = _ZERO,
    price: Decimal | None = None,
    currency: str = "TRY",
    fx_rate_to_try: Decimal = Decimal(1),
    fee_try: Decimal = _ZERO,
    cash_amount_try: Decimal | None = None,
    note: str | None = None,
) -> Transaction:
    """Deftere tek kayıt ekler. Nakit ayağı verilmezse işlem tipinden türetilir:

    BUY  -> -(miktar × fiyat × kur + komisyon)
    SELL -> +(miktar × fiyat × kur - komisyon)
    DEPOSIT/WITHDRAW/DIVIDEND/INTEREST/FEE -> cash_amount_try zorunlu
    """
    if (transaction_type in _ASSET_REQUIRED_TYPES) != (asset_id is not None):
        raise LedgerError(
            f"{transaction_type.value} işlemi için asset_id "
            f"{'zorunlu' if transaction_type in _ASSET_REQUIRED_TYPES else 'verilemez'}"
        )
    if quantity < 0:
        raise LedgerError("quantity negatif olamaz; yön transaction_type'tan okunur")

    if cash_amount_try is None:
        if transaction_type in (TransactionType.BUY, TransactionType.SELL):
            if price is None:
                raise LedgerError(f"{transaction_type.value} için price zorunlu")
            gross = quantity * price * fx_rate_to_try
            signed = (
                -(gross + fee_try) if transaction_type == TransactionType.BUY else gross - fee_try
            )
            cash_amount_try = signed.quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
        else:
            raise LedgerError(f"{transaction_type.value} için cash_amount_try zorunlu")

    expected_sign_negative = transaction_type in _OUTFLOW_TYPES
    if expected_sign_negative and cash_amount_try > 0:
        raise LedgerError(f"{transaction_type.value} nakit ayağı pozitif olamaz")
    if not expected_sign_negative and cash_amount_try < 0:
        raise LedgerError(f"{transaction_type.value} nakit ayağı negatif olamaz")

    if cash_amount_try < 0:
        balance = cash_balance_as_of(db, portfolio_id)
        if balance + cash_amount_try < 0:
            raise LedgerError(
                f"Yetersiz nakit: bakiye {balance} TL, işlem {cash_amount_try} TL istiyor. "
                "Önce DEPOSIT kaydı gerekir."
            )

    transaction = Transaction(
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        transaction_type=transaction_type,
        quantity=quantity,
        price=price,
        currency=currency,
        fx_rate_to_try=fx_rate_to_try,
        fee_try=fee_try,
        cash_amount_try=cash_amount_try,
        transaction_date=transaction_date,
        note=note,
    )
    db.add(transaction)
    db.flush()
    return transaction


def rebuild_holdings(db: Session, portfolio_id: uuid.UUID) -> list[Holding]:
    """holdings önbelleğini defterden yeniden üretir (I1'in üretici tarafı).

    quantity=0 satırlar silinmez: kapatılmış pozisyonun satırı
    realized_pnl_try'yi taşır ("THYAO'dan 6.000 TL kazandım" bilgisi varlık
    satıldı diye buharlaşmaz)."""
    transactions = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id, Transaction.asset_id.isnot(None))
            .order_by(Transaction.transaction_date, Transaction.created_at)
        )
        .scalars()
        .all()
    )

    class _State:
        __slots__ = ("quantity", "total_cost_try", "realized_pnl_try", "avg_cost_try")

        def __init__(self):
            self.quantity = _ZERO
            self.total_cost_try = _ZERO
            self.realized_pnl_try = _ZERO
            self.avg_cost_try = _ZERO

    states: dict[uuid.UUID, _State] = {}
    for tx in transactions:
        state = states.setdefault(tx.asset_id, _State())
        if tx.transaction_type == TransactionType.BUY:
            # Maliyete komisyon dahil: nakit ayağının mutlak değeri.
            state.total_cost_try += -tx.cash_amount_try
            state.quantity += tx.quantity
            state.avg_cost_try = state.total_cost_try / state.quantity
        elif tx.transaction_type == TransactionType.SELL:
            if tx.quantity > state.quantity:
                raise LedgerError(
                    f"Defter tutarsız: {tx.asset_id} için eldekinden fazla satış "
                    f"({tx.quantity} > {state.quantity}, işlem {tx.id})"
                )
            cost_of_sold = state.avg_cost_try * tx.quantity
            state.realized_pnl_try += tx.cash_amount_try - cost_of_sold
            state.total_cost_try -= cost_of_sold
            state.quantity -= tx.quantity
            # avg_cost satışta değişmez; pozisyon sıfırlanırsa bilgi olarak kalır.
        elif tx.transaction_type == TransactionType.DIVIDEND:
            state.realized_pnl_try += tx.cash_amount_try

    existing = {
        h.asset_id: h
        for h in db.execute(select(Holding).where(Holding.portfolio_id == portfolio_id))
        .scalars()
        .all()
    }
    now = datetime.now(timezone.utc)
    result: list[Holding] = []
    for asset_id, state in states.items():
        holding = existing.pop(asset_id, None)
        if holding is None:
            holding = Holding(portfolio_id=portfolio_id, asset_id=asset_id)
            db.add(holding)
        holding.quantity = state.quantity
        holding.avg_cost_price = state.avg_cost_try.quantize(_COST_QUANT, rounding=ROUND_HALF_UP)
        holding.realized_pnl_try = state.realized_pnl_try.quantize(
            _TRY_QUANT, rounding=ROUND_HALF_UP
        )
        holding.last_rebuilt_at = now
        result.append(holding)

    # Defterde hiç izi olmayan holdings satırı bayat önbellektir; silinir.
    for stale in existing.values():
        db.delete(stale)

    db.flush()
    return result


def position_as_of(db: Session, portfolio_id: uuid.UUID, day: date) -> dict[uuid.UUID, Decimal]:
    """Verilen gün SONUNDA varlık başına miktar ('1 Mart'ta portföyüm neydi')."""
    transactions = (
        db.execute(
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.asset_id.isnot(None),
                func.date(Transaction.transaction_date) <= day,
            )
            .order_by(Transaction.transaction_date)
        )
        .scalars()
        .all()
    )
    quantities: dict[uuid.UUID, Decimal] = {}
    for tx in transactions:
        current = quantities.get(tx.asset_id, _ZERO)
        if tx.transaction_type == TransactionType.BUY:
            quantities[tx.asset_id] = current + tx.quantity
        elif tx.transaction_type == TransactionType.SELL:
            quantities[tx.asset_id] = current - tx.quantity
    return {asset_id: qty for asset_id, qty in quantities.items() if qty != 0}


def external_flows(
    db: Session, portfolio_id: uuid.UUID, start: date, end: date
) -> list[tuple[date, Decimal]]:
    """[start, end] aralığındaki dış para akışları (DEPOSIT +, WITHDRAW -).

    Getiri hesabının (TWR) dış akışı portföy performansı sanmaması için
    ayrıştırılır (FR-3)."""
    rows = db.execute(
        select(Transaction.transaction_date, Transaction.cash_amount_try)
        .where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.transaction_type.in_([TransactionType.DEPOSIT, TransactionType.WITHDRAW]),
            func.date(Transaction.transaction_date) >= start,
            func.date(Transaction.transaction_date) <= end,
        )
        .order_by(Transaction.transaction_date)
    ).all()
    return [(tx_date.date(), amount) for tx_date, amount in rows]
