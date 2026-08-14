"""İşlem defteri (ledger) — portföyün yazılan gerçeği.

Kurallar (bkz. docs/DATA.md ve services/ledger_service.py):

- Defter APPEND-ONLY'dir: UPDATE/DELETE yapılmaz, düzeltme ters kayıtla olur.
  DB trigger'ıyla zorlanmaz (POC); tek yazma kapısı
  `ledger_service.record_transaction`'dır.
- `quantity` her zaman >= 0; yön `transaction_type`'tan okunur.
- `cash_amount_try` İŞARETLİDİR: BUY/WITHDRAW/FEE -> negatif (para çıkar),
  SELL/DEPOSIT/DIVIDEND/INTEREST -> pozitif (para girer).
  Nakit bakiyesi = SUM(cash_amount_try); defter her zaman dengelidir.
- `fx_rate_to_try` işlem anındaki kurdur ve DONDURULUR — sonradan yeniden
  üretilemez bir bilgidir (AK 5.7'nin işlem tarafı).
- DEPOSIT/WITHDRAW/INTEREST/FEE varlığa bağlı değildir (asset_id NULL);
  BUY/SELL/DIVIDEND varlık ister. CHECK ile zorlanır.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.portfolio import Portfolio


class TransactionType(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    DEPOSIT = "deposit"  # dış para girişi — getiri hesabından ayrıştırılır (TWR)
    WITHDRAW = "withdraw"  # dış para çıkışı
    DIVIDEND = "dividend"  # temettü (varlığa bağlı nakit girişi)
    INTEREST = "interest"  # mevduat/nakit faizi
    FEE = "fee"  # komisyon/masraf


class Transaction(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "(transaction_type IN ('buy','sell','dividend')) = (asset_id IS NOT NULL)",
            name="ck_transactions_asset_required",
        ),
        CheckConstraint("quantity >= 0", name="ck_transactions_quantity_nonneg"),
        CheckConstraint("fx_rate_to_try > 0", name="ck_transactions_fx_positive"),
        CheckConstraint(
            "transaction_type NOT IN ('buy','withdraw','fee') OR cash_amount_try <= 0",
            name="ck_transactions_outflow_sign",
        ),
        CheckConstraint(
            "transaction_type NOT IN ('sell','deposit','dividend','interest') "
            "OR cash_amount_try >= 0",
            name="ck_transactions_inflow_sign",
        ),
        # Değer serisi / dönemsel getiri sorguları için.
        Index("ix_transactions_portfolio_date", "portfolio_id", "transaction_date"),
        # Pozisyonun defterden yeniden kurulması için.
        Index(
            "ix_transactions_portfolio_asset_date", "portfolio_id", "asset_id", "transaction_date"
        ),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(
            TransactionType,
            name="transaction_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(0), server_default="0"
    )
    # İşlem para biriminde birim fiyat; nakit hareketlerinde (deposit vb.) NULL.
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="TRY", server_default="TRY"
    )
    fx_rate_to_try: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal(1), server_default="1"
    )
    fee_try: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    cash_amount_try: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="transactions")
    asset: Mapped["Asset | None"] = relationship(back_populates="transactions")
