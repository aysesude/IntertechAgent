import uuid

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
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


# ---------------------------------------------------------------------------
# Veri izolasyonu (AK 5.4)
# ---------------------------------------------------------------------------


@pytest.fixture()
def baska_kullanici(db_session):
    u = User(email="baskasi@example.com", full_name="Baska Kullanici")
    db_session.add(u)
    db_session.commit()
    return u


def test_ak_5_4_cannot_continue_another_users_session(db_session, user, baska_kullanici):
    """Oturum kimliğini ele geçiren kişi o sohbete YAZAMAZ.

    Sahiplik kontrolü olmasa, saldırgan başkasının oturumuna kendi mesajını
    ekleyip geçmişi bağlam olarak ajana okutabilirdi — yani kurbanın portföy
    konuşmasını okuyabilirdi. Kontrol servis katmanında, çünkü bu bir HTTP
    kuralı değil defterin bütünlük kuralı.
    """
    oturum = chat_service.get_or_create_session(db_session, user.id, None)

    with pytest.raises(AuthorizationError):
        chat_service.get_or_create_session(db_session, baska_kullanici.id, oturum.id)


def test_ak_5_4_cannot_read_another_users_session_messages(db_session, user, baska_kullanici):
    """Başkasının sohbet geçmişi okunamaz.

    Bu kontrol eklenene kadar gerçek bir açıktı: `GET /api/chat/sessions/{id}/
    messages` oturumun kime ait olduğuna hiç bakmıyordu.
    """
    oturum = chat_service.get_or_create_session(db_session, user.id, None)
    chat_service.create_user_message(db_session, oturum.id, "Gizli soru")

    with pytest.raises(AuthorizationError):
        chat_service.get_session_messages(db_session, oturum.id, owner_id=baska_kullanici.id)

    # Sahibi okuyabilmeli — kontrol yanlış tarafa kapanmasın.
    mesajlar = chat_service.get_session_messages(db_session, oturum.id, owner_id=user.id)
    assert len(mesajlar) == 1
