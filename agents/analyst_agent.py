import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.market_query import sirketleri_tespit_et
from app.core.llm_client import get_llm_client

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

    # `AgentResponse.agent_name` zorunlu alan (bkz. agents/base.py) ve
    # `BaseAgent.error_response` bunu okuyor; tanımsız bırakılınca her yanıt
    # üretiminde ValidationError çıkıyordu.
    agent_name = "analyst"

    async def _fetch_company_data(self, symbol: str, request_message: str) -> str:
        """Bir şirket için hedef fiyat, güncel fiyat, temel analiz ve haberleri eşzamanlı çeker."""
        coros = [
            self.call_mcp_tool("get_target_prices", {"symbols": [symbol]}),
            self.call_mcp_tool("get_current_prices", {"symbols": [symbol]}),
            self.call_mcp_tool("get_fundamentals", {"symbols": [symbol]}),
            self.call_mcp_tool(
                "search_market_news", {"query": f"{symbol} {request_message}", "top_k": 3}
            ),
            # ŞİRKETİN KENDİ FİYAT SERİSİ. Endeksin serisi ayrıca çekiliyor
            # ama şirketinki hiç istenmiyordu; sonuç: ölçülen turda (1 Eylül
            # 2026) beş analiz yanıtının beşi de aynı cümleyle bitiyordu —
            # "hisseye ait üç aylık fiyat serisi bulunmadığı için endekse
            # göre karşılaştırma yapılamıyor". Prompt kuralı 7 bağıl
            # performans yorumu istiyor; girdisi eksikti. Pencere endeksle
            # AYNI (3 ay) olmalı, yoksa iki farklı dönem kıyaslanır.
            self.call_mcp_tool("get_asset_price_history", {"symbols": [symbol], "window": "3m"}),
        ]

        target_res, price_res, fund_res, news_res, history_res = await asyncio.gather(
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

        if (
            not isinstance(history_res, Exception)
            and history_res.get("success")
            and history_res.get("data")
        ):
            lines.append(
                f"3 Aylık Fiyat Serisi (endeksle AYNI dönem): "
                f"{json.dumps(history_res['data'], ensure_ascii=False)}"
            )

        return "\n".join(lines)

    async def execute(self, request: AgentRequest, on_token: Any = None) -> AgentResponse:
        # En fazla 3 şirket alıyoruz ki hız/token sınırı aşılmasın
        symbols = sirketleri_tespit_et(request.query)[:3]

        context_data = []

        # Kullanıcının Risk Profilini Çek
        # Profil YEDEĞE düşebilmeli. `call_mcp_tool` tool hatalarını zarf içinde
        # döndürür ama MCP sunucusuna hiç bağlanılamadığında istisna atar; bu
        # çağrı `execute`'un ilk satırındaydı, dolayısıyla aşağıdaki
        # "Bilinmiyor" yedeğine hiçbir zaman düşülemiyordu. Profil bilinmese de
        # analiz üretilebilir — kişiselleştirme kaybolur, cevap kaybolmaz.
        try:
            risk_res = await self.call_mcp_tool(
                "get_user_risk_survey", {"user_id": request.user_id}
            )
        except Exception:  # noqa: BLE001 — profil isteğe bağlı bir zenginleştirme
            logger.warning("[AJAN] analyst: risk profili alınamadı", exc_info=True)
            risk_res = None
        risk_profile_info = "Bilinmiyor"
        if isinstance(risk_res, dict) and risk_res.get("success") and risk_res.get("data"):
            profile = risk_res["data"].get("risk_profile")
            score = risk_res["data"].get("risk_survey_score")
            if profile:
                risk_profile_info = f"Profil: {profile} (Skor: {score})"

        context_data.append(f"Kullanıcı Risk Profili: {risk_profile_info}")

        if symbols:
            # Tüm şirketler için eşzamanlı veri çek (ayrıca benchmark XU100 güncel fiyatı)
            coros = [self._fetch_company_data(sym, request.query) for sym in symbols]
            coros.append(
                self.call_mcp_tool(
                    "get_asset_price_history", {"symbols": ["XU100"], "window": "3m"}
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

        llm = get_llm_client()
        try:
            yanit = await llm.generate(
                prompt=f"Kullanıcının Sorusu: {request.query}\n\nLütfen kurallara uyarak analizini yap.",
                system=prompt,
            )
            return AgentResponse(
                agent_name=self.agent_name,
                success=True,
                summary_text=f"Analist Yorumu:\n{yanit}",
            )
        except Exception as e:
            logger.error("[AJAN] analyst hatası: %s", e)
            return self.error_response("Analiz sırasında bir hata oluştu.")
