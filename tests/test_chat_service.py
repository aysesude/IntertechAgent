import uuid

import pytest
from app.core.exceptions import NotFoundError
from app.models import MessageRole, MessageStatus, User
from app.services import chat_service


@pytest.fixture()
def user(db_session):
    u = User(email="chat-test@example.com", full_name="Chat Test User")
    db_session.add(u)
    db_session.commit()
    return u


def test_get_or_create_session_creates_when_none_given(db_session, user):
    session = chat_service.get_or_create_session(db_session, user.id, None)
    assert session.user_id == user.id

    # ayni session_id verilince ayni kaydi dondurmeli, yenisini yaratmamali
    same_session = chat_service.get_or_create_session(db_session, user.id, session.id)
    assert same_session.id == session.id


def test_get_or_create_session_raises_not_found_for_unknown_id(db_session, user):
    with pytest.raises(NotFoundError):
        chat_service.get_or_create_session(db_session, user.id, uuid.uuid4())


def test_message_flow_persists_in_chronological_order(db_session, user):
    session = chat_service.get_or_create_session(db_session, user.id, None)

    chat_service.create_user_message(db_session, session.id, "Portföyüm nasıl?")
    chat_service.create_assistant_message(
        db_session,
        session.id,
        "İyi görünüyor.",
        agent_name="portfolio_agent",
        status=MessageStatus.COMPLETE,
        meta={"data": {"total_value": 100}},
    )

    messages = chat_service.get_session_messages(db_session, session.id)
    assert [m.role for m in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[0].status == MessageStatus.COMPLETE
    assert messages[1].agent_name == "portfolio_agent"
    assert messages[1].meta == {"data": {"total_value": 100}}

    recent = chat_service.get_recent_messages(db_session, session.id, limit=1)
    assert len(recent) == 1
    assert recent[0].role == MessageRole.ASSISTANT


def test_get_session_messages_raises_not_found_for_unknown_session(db_session):
    with pytest.raises(NotFoundError):
        chat_service.get_session_messages(db_session, uuid.uuid4())
