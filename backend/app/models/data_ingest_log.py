"""Veri toplama işlerinin iş-düzeyi kaydı (AK 5.2, 5.3).

Satır düzeyindeki `price_history.fetched_at` "bu fiyat ne zaman çekildi"yi
söyler; bu tablo ise "dün gece TCMB çekimi başarısız oldu" gibi hiçbir fiyat
satırında görünmeyen bilgiyi tutar. Dashboard'un "piyasa verisi X gündür
güncellenemedi" uyarısı buradan beslenir (zarif düşüş + uydurmama NFR'ları).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import IngestStatus, PriceSource
from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset


class DataIngestLog(UUIDMixin, Base):
    __tablename__ = "data_ingest_log"
    __table_args__ = (
        Index("ix_data_ingest_log_provider_run_at", "provider", "run_at"),
        Index("ix_data_ingest_log_asset_run_at", "asset_id", "run_at"),
    )

    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[PriceSource] = mapped_column(
        Enum(
            PriceSource,
            name="price_source_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL olabilir: evrende (henüz) olmayan bir sembolün çekim denemesi de
    # loglanabilsin.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    status: Mapped[IngestStatus] = mapped_column(
        Enum(
            IngestStatus,
            name="ingest_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    rows_upserted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped["Asset | None"] = relationship()
