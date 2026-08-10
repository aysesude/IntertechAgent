"""TODO: Piyasa Araştırma Ajanı. mcp_server/tools/market_tools.py ve rag/
pipeline'ı tamamlandığında uygulanacak."""

from collections.abc import Callable

from agents.base import AgentRequest, AgentResponse, BaseAgent


class MarketAgent(BaseAgent):
    agent_name = "market_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        raise NotImplementedError("TODO: Piyasa Araştırma Ajanı henüz uygulanmadı")
