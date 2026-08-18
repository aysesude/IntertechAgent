"""Piyasa Araştırma Ajanı: MCP `search_market_news` tool'unu çağırır, dönen
doküman parçalarını kullanıcıya iletir.

RAG vektör deposuna doğrudan erişmez — Portföy Ajanı'yla aynı kalıp. Tüm veri
erişimi MCP Server üzerinden geçer. `search_market_news` LLM kullanmadan
veritabanını kontrol eder; bu ajan da üstüne LLM'e gitmez — tool'dan gelen
doküman parçalarını olduğu gibi `summary_text`'e taşır. Sorguyla alakalı
kayıt yoksa tool `NOT_FOUND` döner; bu, Portföy Ajanı'ndaki gibi standart
`AgentResponse.error` yolundan taşınır (bkz. docs/MCP-TOOLS.md).
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
            {"query": request.query},
        )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Piyasa verisi alınamadı"))

        data = tool_result["data"]
        summary_text = "\n\n".join(r["content"] for r in data["results"])

        if on_token is not None:
            on_token(summary_text)

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=summary_text,
            data=data,
        )
