"""Tüm SQLAlchemy modellerinin ortak temel sınıfı ve zaman damgası mixin'i."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    # Python tarafında (mikrosaniye hassasiyetli) `default` kullanılıyor, sadece
    # DB'nin server_default'una (dialect'e göre saniye hassasiyetine düşebilir,
    # ör. SQLite) güvenilmiyor — art arda hızlı yazılan kayıtların (ör. bir
    # sohbet turundaki user/assistant mesajları) created_at'i çakışmasın diye.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
