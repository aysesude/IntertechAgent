"""Tüm ajanların ortak sözleşmesi: girdi/çıktı şeması, MCP tool erişimi, hata
yönetimi. Ajanlar veriye asla doğrudan erişmez; tek veri erişim yolu
`BaseAgent.call_mcp_tool` üzerinden MCP Server'a gitmektir."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from fastmcp import Client
from pydantic import BaseModel, ConfigDict, Field


class AgentRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    session_id: str
    query: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_name: str
    success: bool
    summary_text: str
    data: dict[str, Any] | None = None
    error: str | None = None


class BaseAgent(ABC):
    agent_name: str

    def __init__(self, mcp_server_url: str) -> None:
        self._mcp_server_url = mcp_server_url

    async def call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """MCP Server'daki bir tool'u çağırır ve yapısal sonucu döndürür."""
        async with Client(self._mcp_server_url) as client:
            result = await client.call_tool(tool_name, arguments)
            return result.structured_content or {}

    def error_response(self, message: str) -> AgentResponse:
        return AgentResponse(agent_name=self.agent_name, success=False, summary_text="", error=message)

    @abstractmethod
    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        """Ajanın ana giriş noktası. Orchestrator bunu çağırır.

        `on_token` verilirse (SSE stream'i için), LLM yanıtı üretilirken her
        parça geldikçe çağrılır. Verilmezse ajan sessizce tam yanıtı biriktirip
        döner — davranış aynı, sadece ara bildirim yok.
        """
