import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.portfolio import Portfolio

class Holding(UUIDMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("portfolio_id", "asset_id", name="uq_holding_portfolio_asset"),)

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    avg_cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")
    asset: Mapped["Asset"] = relationship(back_populates="holdings")
