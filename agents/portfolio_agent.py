"""Portföy Ajanı: MCP `get_portfolio_summary` tool'unu çağırır, dönen veriyi
LLM ile doğal dile döker. Sayısal hiçbir değer LLM tarafından üretilmez —
LLM sadece tool'dan gelen veriyi özetler."""

import json
from collections.abc import Callable
from pathlib import Path

from app.core.llm_client import get_llm_client

from agents.base import AgentRequest, AgentResponse, BaseAgent

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "portfolio_agent.md").read_text(encoding="utf-8")


class PortfolioAgent(BaseAgent):
    agent_name = "portfolio_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        tool_result = await self.call_mcp_tool(
            "get_portfolio_summary", {"user_id": request.user_id}
        )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Portföy verisi alınamadı"))

        data = tool_result["data"]
        summary_text = await self._summarize(request.query, data, on_token=on_token)
        return AgentResponse(agent_name=self.agent_name, success=True, summary_text=summary_text, data=data)

    async def _summarize(
        self, query: str, portfolio_data: dict, *, on_token: Callable[[str], None] | None = None
    ) -> str:
        prompt = _PROMPT_TEMPLATE.format(
            query=query, portfolio_json=json.dumps(portfolio_data, ensure_ascii=False, indent=2)
        )
        llm = get_llm_client()
        full_text = ""
        async for chunk in llm.stream(prompt):
            full_text += chunk
            if on_token is not None:
                on_token(chunk)
        return full_text
