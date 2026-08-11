import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset

class PriceHistory(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("asset_id", "price_date", name="uq_price_history_asset_date"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    price_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="price_history")
