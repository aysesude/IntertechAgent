import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import AssetClass, PriceSource
from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.holding import Holding
    from app.models.price_history import PriceHistory
    from app.models.transaction import Transaction


class Asset(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        # 'derived' bir varlığın kaynağı ve katsayısı zorunludur; diğerlerinde olamaz.
        CheckConstraint(
            "(data_source = 'derived') = "
            "(derived_from_asset_id IS NOT NULL AND derived_factor IS NOT NULL)",
            name="ck_assets_derived_consistency",
        ),
    )

    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        Enum(
            AssetClass, name="asset_class_enum", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    # Sunum/filtreleme metadata'sı; bilinen değerler config.AssetSubType'ta.
    # Bilerek String: yeni enstrüman tipi migration gerektirmesin.
    sub_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Varlık silinmez (fiyat geçmişi + işlem FK'sı var); kapatılır.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Bu varlığın fiyatını hangi sağlayıcı besler (AK 5.1 SQL ile denetlenebilir).
    data_source: Mapped[PriceSource] = mapped_column(
        Enum(
            PriceSource,
            name="price_source_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=PriceSource.SYNTHETIC,
        server_default=PriceSource.SYNTHETIC.value,
    )
    # Sağlayıcıdaki sembol (ör. THYAO -> 'THYAO.IS', XAUTRY -> 'GC=F').
    provider_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Türetilmiş varlıklar (ör. çeyrek altın = gram altın × 1.6030).
    derived_from_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id"), nullable=True
    )
    derived_factor: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="asset")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="asset")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="asset")
