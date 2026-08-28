"""Analist hedef fiyatı — bkz. `app/services/target_price_ingest.py` modül
docstring'i (neden RAG değil, neden snapshot/upsert, neden lisans notu)."""

import uuid
from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.asset import Asset


class TargetPrice(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "target_prices"
    __table_args__ = (
        # Tarihçe DEĞİL, kurum başına TEK satır — her ingest upsert eder.
        # Eski değer `previous_target_price`/`revision_direction` alanlarına
        # taşınır (bkz. target_price_ingest.py), ayrı satır olarak birikmez.
        UniqueConstraint("asset_id", "institution", name="uq_target_prices_asset_institution"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    # Kaynak kurum adı (ör. "Şeker Yatırım"). Bilerek String: yeni kurum
    # migration gerektirmesin — bkz. Asset.sub_type'taki aynı gerekçe.
    institution: Mapped[str] = mapped_column(String(64), nullable=False)
    # AL/TUT/SAT/G.G. gibi değerler — kaynağa göre değişebilir, String.
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="TRY")
    # Rapor/tablo anındaki kapanış fiyatı — kazandırma potansiyelini
    # kaynağın kendi bağlamında yorumlamak için (AK 5.1: rakamın hangi
    # fiyata göre hesaplandığı belirsiz kalmasın).
    price_at_report: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    previous_target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    # "yukseltme" / "dusurme" / "koruma" — upsert sırasında hesaplanır.
    revision_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Kaynakta belirtilmiyorsa NULL kalır — 12 ay varsayılmaz (CLAUDE.md
    # "Uydurmama").
    horizon_months: Mapped[int | None] = mapped_column(nullable=True)
    # Sayfa/tablo seviyesinde tarih (hisse başına ayrı rapor tarihi değil —
    # kaynağın kendi granülaritesi bu).
    report_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    asset: Mapped["Asset"] = relationship(back_populates="target_prices")
