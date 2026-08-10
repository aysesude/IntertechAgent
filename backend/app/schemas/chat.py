from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.message import MessageRole, MessageStatus


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    session_id: UUID | None = None
    message: str


class MessageOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    role: MessageRole
    content: str
    agent_name: str | None
    meta: dict[str, Any] | None
    status: MessageStatus
    created_at: datetime
