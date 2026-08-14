from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import RiskProfile
from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.portfolio import Portfolio


class User(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_profile: Mapped[RiskProfile] = mapped_column(
        Enum(
            RiskProfile,
            name="risk_profile_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=RiskProfile.BALANCED,
        server_default=RiskProfile.BALANCED.value,
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="user", uselist=False)
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")
