"""TODO: Risk/Strateji Ajanı. Risk metriği tanımları (volatilite, yoğunlaşma
eşikleri vb.) kullanıcıyla netleştirilmeden uygulanmayacak
(bkz. app/core/config.py TODO notu ve mcp_server/tools/risk_tools.py)."""

from collections.abc import Callable

from agents.base import AgentRequest, AgentResponse, BaseAgent


class RiskAgent(BaseAgent):
    agent_name = "risk_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        raise NotImplementedError("TODO: Risk/Strateji Ajanı henüz uygulanmadı")
