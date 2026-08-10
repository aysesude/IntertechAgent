import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class Portfolio(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "portfolios"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="portfolio")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="portfolio")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="portfolio")
