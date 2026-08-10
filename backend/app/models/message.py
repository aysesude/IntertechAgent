import enum
import uuid
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(str, enum.Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class Message(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Hangi ajanın ürettiği; kullanıcı mesajlarında None.
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Tool çağrıları, kaynaklar vb. serbest biçimli veri. Postgres'te gerçek
    # JSONB, diğer dialect'lerde (ör. test için SQLite) generic JSON.
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    # İstemci stream'i tamamlanmadan bağlantıyı keserse INCOMPLETE olarak
    # o ana kadar biriken metinle kaydedilir.
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=MessageStatus.COMPLETE,
        server_default=MessageStatus.COMPLETE.value,
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
