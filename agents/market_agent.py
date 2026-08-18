"""Piyasa Araştırma Ajanı: MCP `search_market_news` tool'unu çağırır, dönen
doküman parçalarını kullanıcıya iletir.

RAG vektör deposuna doğrudan erişmez — Portföy Ajanı'yla aynı kalıp. Tüm veri
erişimi MCP Server üzerinden geçer. `search_market_news` LLM kullanmadan
veritabanını kontrol eder; bu ajan da üstüne LLM'e gitmez — tool'dan gelen
veriyi (bulunan doküman parçaları ya da "bulunamadı" mesajı) olduğu gibi iletir.
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

        if data.get("found"):
            summary_text = "\n\n".join(r["content"] for r in data["results"])
        else:
            summary_text = data.get("message") or "Veritabanında ilgili bilgi bulunamadı."

        if on_token is not None:
            on_token(summary_text)

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=summary_text,
            data=data,
        )
