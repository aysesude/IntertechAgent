import uuid
from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import PriceSource
from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset


class PriceHistory(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("asset_id", "price_date", name="uq_price_history_asset_date"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    price_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    # 18,6: TEFAS fon fiyatları 6 ondalık yayımlanıyor; 4'e yuvarlamak sessiz
    # hassasiyet kaybıdır.
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # Bu fiyat hangi kaynaktan geldi (AK 5.1) ve ne zaman çekildi (AK 5.3).
    source: Mapped[PriceSource] = mapped_column(
        Enum(
            PriceSource,
            name="price_source_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=PriceSource.SYNTHETIC,
        server_default=PriceSource.SYNTHETIC.value,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    asset: Mapped["Asset"] = relationship(back_populates="price_history")
