from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import AssetClass
from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.holding import Holding
    from app.models.price_history import PriceHistory
    from app.models.transaction import Transaction

class Asset(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        Enum(AssetClass, name="asset_class_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)

    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="asset")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="asset")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="asset")
