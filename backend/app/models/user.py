from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import RiskProfile
from app.models.base import Base, CreatedAtMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.portfolio import Portfolio


class User(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Aralık veritabanı düzeyinde de kilitli: doğrulama Pydantic'te ve
        # `advice_eligibility.validate_survey_score` içinde zaten var, ama
        # uygulamayı atlayan bir yol (elle SQL, veri aktarımı) aralık dışı bir
        # puan yazarsa uygunluk kontrolü sessizce hak edilmemiş genişlikte
        # tavsiye üretirdi.
        CheckConstraint(
            "risk_survey_score IS NULL OR (risk_survey_score BETWEEN 1 AND 7)",
            name="ck_users_risk_survey_score_range",
        ),
    )

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

    # --- Anket risk puanı (1-7) ---
    #
    # Şartnamenin ölçeği ve uygunluk kontrolünün (`advice_eligibility`)
    # girdisi. `risk_profile` ise risk motorunun anahtarı olarak duruyor ve
    # bu puandan TÜRETİLİYOR (`config.risk_profile_for_survey_score`) — iki
    # ölçek yan yana yaşıyor, biri yetkili diğeri türev.
    #
    # NEDEN NULLABLE. Mevcut satırlara bir anket sonucu uydurulamaz;
    # kullanıcı o anketi doldurmadı. `NULL` anlamlıdır: "kayıtlı anket
    # sonucu yok" — okuyan taraf `risk_profile`'a düşer. `make seed` demo
    # kullanıcılarının hepsini doldurur.
    risk_survey_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Anket olayı zaman damgaları (Sinyal 5, Yol A) ---
    #
    # `risk_survey_score`'un KENDİSİ statik bir durumdur — anketin NE ZAMAN
    # dolduğunu taşımaz. Sinyal 5 (profil_sapmasi) yalnızca anketin YENİDEN
    # doldurulduğu ANDA tetiklenmeli (bkz. agents/risk_agent.py modül
    # docstring'i, docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md);
    # bu iki kolon o "olay"ı yakalar.
    #
    # NEDEN İKİ AYRI KOLON (tek bir boolean değil). "Ne zaman oldu" ile "ne
    # zaman görüldü" bilgisi ayrı ayrı taşınmalı: `risk_survey_updated_at`
    # anketin en son ne zaman güncellendiğini, `risk_survey_event_consumed_at`
    # bu güncellemenin en son ne zaman bir risk değerlendirmesine
    # yansıtıldığını (tüketildiğini) tutar. "Bekleyen olay var" tanımı:
    # `risk_survey_updated_at IS NOT NULL AND (risk_survey_event_consumed_at
    # IS NULL OR risk_survey_event_consumed_at < risk_survey_updated_at)`.
    #
    # NEDEN NULLABLE. Mevcut satırlara bir anket-güncelleme/tüketim anı
    # uydurulamaz. `NULL` "bu kullanıcı için hiç anket-olayı yaşanmadı/
    # tüketilmedi" demektir. `set_user_risk_survey` yazar,
    # `set_user_risk_profile` (elle profil değiştirme) DOKUNMAZ — o bir anket
    # olayı değildir.
    risk_survey_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    risk_survey_event_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="user", uselist=False)
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")
