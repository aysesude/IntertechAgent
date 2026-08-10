"""Sohbet oturumu ve mesajlarıyla ilgili tüm SQL sorguları burada."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import ChatSession, Message, MessageRole, MessageStatus


def get_or_create_session(db: Session, user_id: UUID, session_id: UUID | None) -> ChatSession:
    if session_id is not None:
        session = db.get(ChatSession, session_id)
        if session is None:
            raise NotFoundError(f"Chat session not found for session_id {session_id}")
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


def get_session_messages(db: Session, session_id: UUID) -> list[Message]:
    """Geçmiş ekranı için: oturumdaki tüm mesajları kronolojik sırada döner."""
    session = db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError(f"Chat session not found for session_id {session_id}")

    return (
        db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at))
        .scalars()
        .all()
    )
