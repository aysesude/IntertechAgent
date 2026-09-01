import json
import logging
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.market_query import sirket_tespit_et

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "analyst_agent.md").read_text(
    encoding="utf-8"
)

class AnalystAgent(BaseAgent):
    """
    Kullanıcının tekil şirket/varlık veya piyasa verileri (hedef fiyat,
    bilanço, haberler) üzerindeki 'YORUM' ve 'ANALİZ' isteklerini, yatırım
    tavsiyesi vermeden değerlendiren ajandır.
    """

    async def execute(
        self, request: AgentRequest, on_token: Any = None
    ) -> AgentResponse:
        sorgu = sirket_tespit_et(request.message)
        context_data = []

        if sorgu is not None:
            # 1. Hedef fiyatları getir
            target_result = await self.call_mcp_tool(
                "get_target_prices", {"symbols": [sorgu.symbol]}
            )
            if target_result.get("success") and target_result.get("data"):
                context_data.append(
                    f"Hedef Fiyatlar: {json.dumps(target_result['data'], ensure_ascii=False)}"
                )

            # 2. Güncel fiyatı getir
            price_result = await self.call_mcp_tool(
                "get_current_prices", {"symbols": [sorgu.symbol]}
            )
            if price_result.get("success") and price_result.get("data"):
                context_data.append(
                    f"Güncel Fiyat: {json.dumps(price_result['data'], ensure_ascii=False)}"
                )

            # 3. Haber ve RAG belgelerini getir
            news_query = f"{sorgu.ad} {request.message}"
            news_result = await self.call_mcp_tool(
                "search_market_news", {"query": news_query, "top_k": 5}
            )
            if news_result.get("success") and news_result.get("data"):
                context_data.append(
                    f"İlgili Haberler/Belgeler: {json.dumps(news_result['data'], ensure_ascii=False)}"
                )

        veriler = (
            "\n\n".join(context_data)
            if context_data
            else "Kullanıcının sorusuyla ilgili doğrudan bir şirket verisi bulunamadı."
        )
        prompt = _PROMPT_TEMPLATE.replace("{{veriler}}", veriler)

        llm = self._get_llm(request)
        try:
            yanit = await llm.generate(
                prompt=f"Kullanıcının Sorusu: {request.message}\n\nLütfen kurallara uyarak analizini yap.",
                system=prompt,
            )
            return AgentResponse(success=True, summary_text=f"Analist Yorumu:\n{yanit}")
        except Exception as e:
            logger.error("[AJAN] analyst hatası: %s", e)
            return AgentResponse(success=False, error="Analiz sırasında bir hata oluştu.")
