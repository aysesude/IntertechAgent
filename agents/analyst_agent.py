import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.market_query import sirketleri_tespit_et

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "analyst_agent.md").read_text(
    encoding="utf-8"
)


class AnalystAgent(BaseAgent):
    """
    Kullanıcının tekil şirket/varlık veya piyasa verileri (hedef fiyat,
    bilanço, haberler, temel veriler) üzerindeki 'YORUM' ve 'ANALİZ' isteklerini,
    yatırım tavsiyesi vermeden değerlendiren ajandır.
    """

    async def _fetch_company_data(self, symbol: str, request_message: str) -> str:
        """Bir şirket için hedef fiyat, güncel fiyat, temel analiz ve haberleri eşzamanlı çeker."""
        coros = [
            self.call_mcp_tool("get_target_prices", {"symbols": [symbol]}),
            self.call_mcp_tool("get_current_prices", {"symbols": [symbol]}),
            self.call_mcp_tool("get_fundamentals", {"symbols": [symbol]}),
            self.call_mcp_tool(
                "search_market_news", {"query": f"{symbol} {request_message}", "top_k": 3}
            ),
        ]

        target_res, price_res, fund_res, news_res = await asyncio.gather(
            *coros, return_exceptions=True
        )

        lines = [f"--- {symbol} VERİLERİ ---"]

        if (
            not isinstance(target_res, Exception)
            and target_res.get("success")
            and target_res.get("data")
        ):
            lines.append(f"Hedef Fiyatlar: {json.dumps(target_res['data'], ensure_ascii=False)}")

        if (
            not isinstance(price_res, Exception)
            and price_res.get("success")
            and price_res.get("data")
        ):
            lines.append(f"Güncel Fiyat: {json.dumps(price_res['data'], ensure_ascii=False)}")

        if not isinstance(fund_res, Exception) and fund_res.get("success") and fund_res.get("data"):
            lines.append(
                f"Temel Analiz (F/K, PD/DD vb): {json.dumps(fund_res['data'], ensure_ascii=False)}"
            )

        if not isinstance(news_res, Exception) and news_res.get("success") and news_res.get("data"):
            lines.append(
                f"İlgili Haberler/Belgeler: {json.dumps(news_res['data'], ensure_ascii=False)}"
            )

        return "\n".join(lines)

    async def execute(self, request: AgentRequest, on_token: Any = None) -> AgentResponse:
        # En fazla 3 şirket alıyoruz ki hız/token sınırı aşılmasın
        symbols = sirketleri_tespit_et(request.message)[:3]

        context_data = []

        # Kullanıcının Risk Profilini Çek
        risk_res = await self.call_mcp_tool("get_user_risk_survey", {"user_id": request.user_id})
        risk_profile_info = "Bilinmiyor"
        if isinstance(risk_res, dict) and risk_res.get("success") and risk_res.get("data"):
            profile = risk_res["data"].get("risk_profile")
            score = risk_res["data"].get("risk_survey_score")
            if profile:
                risk_profile_info = f"Profil: {profile} (Skor: {score})"

        context_data.append(f"Kullanıcı Risk Profili: {risk_profile_info}")

        if symbols:
            # Tüm şirketler için eşzamanlı veri çek (ayrıca benchmark XU100 güncel fiyatı)
            coros = [self._fetch_company_data(sym, request.message) for sym in symbols]
            coros.append(
                self.call_mcp_tool(
                    "get_asset_price_history", {"symbols": ["XU100.IS"], "window": "3m"}
                )
            )

            results = await asyncio.gather(*coros, return_exceptions=True)

            for res in results[:-1]:  # Şirket verileri
                if isinstance(res, str):
                    context_data.append(res)

            # Benchmark (BIST100) verisi
            benchmark_res = results[-1]
            if (
                not isinstance(benchmark_res, Exception)
                and benchmark_res.get("success")
                and benchmark_res.get("data")
            ):
                context_data.append(
                    f"Endeks Kıyaslaması (XU100 - BIST100 3 Aylık Seyir): {json.dumps(benchmark_res['data'], ensure_ascii=False)}"
                )

        veriler = (
            "\n\n".join(context_data)
            if len(context_data) > 1
            else context_data[0]
            + "\n\nKullanıcının sorusuyla ilgili doğrudan bir şirket tespit edilemedi."
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
