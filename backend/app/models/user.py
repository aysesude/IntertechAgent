from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String
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

    # --- Kimlik doğrulama ---
    #
    # NEDEN NULLABLE. Bu sütunlar mevcut satırların üzerine eklendi ve bir
    # migration içinde bcrypt özeti üretilemez. `NULL` anlamlıdır ve öyle
    # kalacaktır: "bu kullanıcıya kimlik bilgisi atanmamış, giriş yapamaz."
    # `make seed` 50 demo kullanıcısının hepsini doldurur.
    #
    # `national_id` T.C. kimlik numarasıdır; String(11) çünkü baştaki sıfırı
    # koruması gerekir ve üzerinde aritmetik yapılmaz. `unique` giriş
    # sorgusunun tek satır bulmasını garanti eder.
    national_id: Mapped[str | None] = mapped_column(String(11), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # timezone=True: token süresi ve "son giriş" gösterimi UTC üzerinden
    # hesaplanır, sunucunun yerel saatine göre kaymasın.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="user", uselist=False)
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")
