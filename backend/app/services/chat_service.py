"""Sohbet oturumu ve mesajlarıyla ilgili tüm SQL sorguları burada."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models import ChatSession, Message, MessageRole, MessageStatus


def get_or_create_session(db: Session, user_id: UUID, session_id: UUID | None) -> ChatSession:
    if session_id is not None:
        session = db.get(ChatSession, session_id)
        if session is None:
            raise NotFoundError(f"Chat session not found for session_id {session_id}")
        # AK 5.4. Sahiplik kontrolü olmadan, bir oturum kimliğini ele geçiren
        # kişi o sohbete kendi mesajını ekleyebilir ve geçmişi bağlam olarak
        # ajana okutabilirdi. Kontrol servis katmanında, çünkü bu bir HTTP
        # kuralı değil defterin bütünlük kuralı: oturum sahibinden başkası
        # ona yazamaz.
        if session.user_id != user_id:
            raise AuthorizationError("Bu sohbet oturumuna erişim yetkiniz yok.")
        return session

    session = ChatSession(user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def create_user_message(db: Session, session_id: UUID, content: str) -> Message:
    message = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content=content,
        status=MessageStatus.COMPLETE,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def create_assistant_message(
    db: Session,
    session_id: UUID,
    content: str,
    *,
    agent_name: str | None,
    status: MessageStatus,
    meta: dict[str, Any] | None = None,
) -> Message:
    message = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=content,
        agent_name=agent_name,
        meta=meta,
        status=status,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_recent_messages(db: Session, session_id: UUID, limit: int) -> list[Message]:
    """Bağlam için: son `limit` mesajı, en eskiden en yeniye sıralı döner."""
    rows = (
        db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


def get_session_messages(
    db: Session, session_id: UUID, *, owner_id: UUID | None = None
) -> list[Message]:
    """Geçmiş ekranı için: oturumdaki tüm mesajları kronolojik sırada döner.

    `owner_id` verilirse oturumun o kullanıcıya ait olduğu doğrulanır (AK 5.4).
    `None` yalnızca kimlik zorunluluğunun kapalı olduğu geçiş döneminde gelir
    (bkz. api/deps.py, AUTH_ENFORCE).
    """
    session = db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError(f"Chat session not found for session_id {session_id}")
    if owner_id is not None and session.user_id != owner_id:
        raise AuthorizationError("Bu sohbet oturumuna erişim yetkiniz yok.")

    return (
        db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        )
        .scalars()
        .all()
    )
