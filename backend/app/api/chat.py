"""POST /api/chat: isteği Orchestrator'a iletir, cevabı SSE ile stream eder;
kullanıcı mesajını ajanlar çalışmadan ÖNCE, asistan mesajını stream bitince
(veya bağlantı yarıda kesilirse o ana kadarki metinle "incomplete" olarak)
DB'ye yazar.

GET /api/chat/sessions/{session_id}/messages: oturum geçmişini kronolojik döner.

Not: DB session'ı burada FastAPI `Depends` ile değil, elle (`SessionLocal`)
açılıp kapatılıyor — SSE generator'ı route fonksiyonu döndükten çok sonra,
response tamamen stream edilene kadar çalışmaya devam ediyor; request-scope'lu
bir `Depends` session'ının bu sürede güvenle açık kalacağına güvenmek yerine
ömrünü kendimiz yönetiyoruz (mcp_server/tools/portfolio_tools.py ile aynı desen).
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from agents.orchestrator import stream_orchestrator
from app.api.deps import get_current_user, verify_user_access
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.exceptions import AuthorizationError, NotFoundError
from app.models import MessageStatus, User
from app.schemas.chat import ChatRequest, MessageOut
from app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@router.post("")
async def chat(
    request: ChatRequest,
    current_user: User | None = Depends(get_current_user),
) -> EventSourceResponse:
    # Gövdedeki user_id artık doğrulanan bir iddia: ajanlara ve oradan MCP
    # tool'larına giden kimlik budur, dolayısıyla zincirin tamamı bu tek
    # kontrole dayanır (AK 5.4).
    verify_user_access(request.user_id, current_user)
    db = SessionLocal()
    try:
        try:
            session = chat_service.get_or_create_session(db, request.user_id, request.session_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=exc.message) from exc

        history_rows = chat_service.get_recent_messages(
            db, session.id, settings.chat_context_message_limit
        )
        history = [{"role": m.role.value, "content": m.content} for m in history_rows]

        # Kullanıcı mesajı ajanlar çalışmadan ÖNCE yazılır ki bir çökme durumunda kaybolmasın.
        chat_service.create_user_message(db, session.id, request.message)
    except Exception:
        db.close()
        raise

    async def event_generator():
        try:
            yield _sse("session", {"session_id": str(session.id)})

            accumulated_text = ""
            final_state = None
            completed_normally = False
            try:
                async for mode, chunk in stream_orchestrator(
                    str(request.user_id), str(session.id), request.message, history
                ):
                    if mode == "custom":
                        accumulated_text += chunk["delta"]
                        yield _sse("token", {"delta": chunk["delta"]})
                    elif mode == "values":
                        final_state = chunk
                completed_normally = True
            except Exception as exc:  # noqa: BLE001 - hatayı SSE üzerinden istemciye ilet
                yield _sse("error", {"message": str(exc)})
            finally:
                responses = final_state["agent_responses"] if final_state else []
                primary = responses[0] if responses else None
                if completed_normally and final_state is not None:
                    content = final_state["final_answer"]
                    status = MessageStatus.COMPLETE
                else:
                    content = accumulated_text
                    status = MessageStatus.INCOMPLETE
                chat_service.create_assistant_message(
                    db,
                    session.id,
                    content,
                    agent_name=primary.agent_name if primary else None,
                    status=status,
                    meta={"data": primary.data} if primary and primary.data else None,
                )

            if completed_normally:
                yield _sse(
                    "done",
                    {
                        "agent": primary.agent_name if primary else None,
                        "final_answer": final_state["final_answer"] if final_state else "",
                        "data": primary.data if primary else None,
                    },
                )
        finally:
            db.close()

    return EventSourceResponse(event_generator())


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def read_session_messages(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> list[MessageOut]:
    """Oturum geçmişi.

    Sahiplik kontrolü servis katmanında yapılır: buradaki `user_id` yoldan
    gelmiyor, oturumun kendi kaydından okunuyor — bu yüzden `verify_user_access`
    değil `owner_id` kullanılıyor.
    """
    owner_id = current_user.id if current_user else None
    try:
        return chat_service.get_session_messages(db, session_id, owner_id=owner_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
