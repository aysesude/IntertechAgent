"""Piyasa Araştırma Ajanı: MCP `search_market_news` tool'unu çağırır, dönen
yanıtı kullanıcıya iletir.

RAG pipeline'ına doğrudan erişmez — Portföy Ajanı'yla aynı kalıp. Tüm veri
erişimi MCP Server üzerinden geçer.
"""

from collections.abc import Callable

from agents.base import AgentRequest, AgentResponse, BaseAgent


class MarketAgent(BaseAgent):
    agent_name = "market_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        tool_result = await self.call_mcp_tool(
            "search_market_news",
            {"query": request.query, "session_id": request.session_id},
        )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(
                error.get("message", "Piyasa verisi alınamadı")
            )

        answer = tool_result["data"]["answer"]

        # TODO: RAG pipeline'ı yanıtı tek parça üretiyor, token akışı yok.
        # Kullanıcı akan metin yerine cevabı bir anda görüyor. Pipeline'ın
        # üretim kısmı stream'e çevrilirse burası da parça parça besleyebilir.
        if on_token is not None:
            on_token(answer)

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=answer,
            data={"query": request.query},
        )
