"""Orchestrator: kullanıcı isteğini alır, niyeti tespit eder, ilgili ajanlara
dağıtır, sonuçları birleştirip tek bir cevap üretir (LangGraph).

Graf yapısı:

    detect_intent ─┬─> portfolio_agent ─┬─> market_agent ─> merge ─> END
                   │                    └─> merge
                   └─> market_agent ────────> merge

Yani niyet "portfolio" ise yalnızca Portföy Ajanı, "market" ise yalnızca Piyasa
Ajanı, "both" ise ikisi **sırayla** çalışır.

Neden paralel değil de sıralı: her iki ajan da token akışı üretiyor. Paralel
çalıştırıldıklarında token'lar iç içe geçip okunamaz bir metin oluşuyor.
Sıralı çalıştırmak akışı bozmuyor; paralellik ancak akış birleştirme mantığı
yazılırsa anlamlı olur (TODO).

`run_portfolio_agent` ve `run_market_agent` node'ları `writer: StreamWriter`
parametresi alır: LangGraph tarafından otomatik enjekte edilir,
`stream_mode="custom"` kullanılmadığında no-op'tur — böylece `run_orchestrator()`
(tek seferlik) ve `stream_orchestrator()` (SSE) aynı graf üzerinden çalışır.
"""

import operator
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import StreamWriter

from agents.base import AgentRequest, AgentResponse
from agents.market_agent import MarketAgent
from agents.portfolio_agent import PortfolioAgent
from app.core.config import settings

# Niyet tespiti şimdilik anahtar kelime tabanlı. LLM ile yapmak her soruya
# 2-5 saniye ek gecikme bindirirdi ve bu aşamada ayırt edilmesi gereken yalnızca
# iki alan var. Ajan sayısı arttığında LLM tabanlı sınıflandırmaya geçilmeli.
_PORTFOLIO_KEYWORDS = {
    "portföy", "portfoy", "varlık", "varlik", "dağılım", "dagilim",
    "getiri", "kazanç", "kazanc", "zarar", "bakiye", "hesabım", "hesabim",
    "yatırımım", "yatirimim", "toplam değer", "kar zarar", "kâr zarar",
    "ne kadar param", "birikim",
}

_MARKET_KEYWORDS = {
    "haber", "piyasa", "bilanço", "bilanco", "çeyrek", "ceyrek", "borsa",
    "analiz", "rapor", "faiz", "enflasyon", "tcmb", "gelişme", "gelisme",
    "açıkla", "acikla", "sonuç", "sonuc", "beklenti", "sektör", "sektor",
    "endeks", "dolar kuru", "kur", "temettü", "temettu",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    message: str
    # Son N mesajlık sohbet geçmişi ({"role": ..., "content": ...} sözlükleri).
    # TODO: Ajanlar şu an bunu prompt'larına dahil etmiyor (tek turluk
    # çalışıyorlar); alan, çok turlu bağlam gereken ajanlar için hazır tutuluyor.
    history: list[dict[str, str]]
    intent: str
    agent_responses: Annotated[list[AgentResponse], operator.add]
    final_answer: str


def detect_intent(state: OrchestratorState) -> dict:
    """Sorguyu 'portfolio', 'market' veya 'both' olarak sınıflandırır.

    Hiçbir anahtar kelime eşleşmezse 'portfolio' varsayılır: kullanıcıların
    çoğu sorusu kendi verisiyle ilgili ve Portföy Ajanı her zaman anlamlı bir
    cevap üretebiliyor, Piyasa Ajanı ise doküman yoksa boş dönüyor.
    """
    query = _normalize(state["message"])

    has_portfolio = any(k in query for k in _PORTFOLIO_KEYWORDS)
    has_market = any(k in query for k in _MARKET_KEYWORDS)

    if has_portfolio and has_market:
        intent = "both"
    elif has_market:
        intent = "market"
    else:
        intent = "portfolio"

    return {"intent": intent}


def _build_request(state: OrchestratorState) -> AgentRequest:
    return AgentRequest(
        user_id=state["user_id"],
        session_id=state["session_id"],
        query=state["message"],
        context={"recent_messages": state["history"]},
    )


async def run_portfolio_agent(state: OrchestratorState, writer: StreamWriter) -> dict:
    agent = PortfolioAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(
        _build_request(state), on_token=lambda token: writer({"delta": token})
    )
    return {"agent_responses": [response]}


async def run_market_agent(state: OrchestratorState, writer: StreamWriter) -> dict:
    # İki ajan da çalışıyorsa cevapları görsel olarak ayır.
    if state["intent"] == "both":
        writer({"delta": "\n\n"})

    agent = MarketAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(
        _build_request(state), on_token=lambda token: writer({"delta": token})
    )
    return {"agent_responses": [response]}


def merge_responses(state: OrchestratorState) -> dict:
    successful = [r.summary_text for r in state["agent_responses"] if r.success]
    if successful:
        final_answer = "\n\n".join(successful)
    else:
        errors = [r.error for r in state["agent_responses"] if r.error]
        final_answer = errors[0] if errors else "Üzgünüm, isteğinizi işlerken bir sorun oluştu."
    return {"final_answer": final_answer}


def _route_after_intent(state: OrchestratorState) -> str:
    """Niyet 'market' ise doğrudan Piyasa Ajanı'na, diğer durumlarda önce
    Portföy Ajanı'na gider."""
    return "market_agent" if state["intent"] == "market" else "portfolio_agent"


def _route_after_portfolio(state: OrchestratorState) -> str:
    """Niyet 'both' ise Portföy Ajanı'ndan sonra Piyasa Ajanı da çalışır."""
    return "market_agent" if state["intent"] == "both" else "merge"


def _build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("detect_intent", detect_intent)
    graph.add_node("portfolio_agent", run_portfolio_agent)
    graph.add_node("market_agent", run_market_agent)
    graph.add_node("merge", merge_responses)

    graph.set_entry_point("detect_intent")
    graph.add_conditional_edges(
        "detect_intent",
        _route_after_intent,
        {"portfolio_agent": "portfolio_agent", "market_agent": "market_agent"},
    )
    graph.add_conditional_edges(
        "portfolio_agent",
        _route_after_portfolio,
        {"market_agent": "market_agent", "merge": "merge"},
    )
    graph.add_edge("market_agent", "merge")
    graph.add_edge("merge", END)
    return graph.compile()


_compiled_graph = _build_graph()


def _initial_state(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]]
) -> OrchestratorState:
    return {
        "user_id": user_id,
        "session_id": session_id,
        "message": message,
        "history": history,
        "intent": "",
        "agent_responses": [],
        "final_answer": "",
    }


async def run_orchestrator(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]] | None = None
) -> OrchestratorState:
    """Stream gerektirmeyen çağırıcılar için (ör. testler): tek seferde tam sonucu döner."""
    return await _compiled_graph.ainvoke(
        _initial_state(user_id, session_id, message, history or [])
    )


async def stream_orchestrator(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]] | None = None
) -> AsyncIterator[tuple[str, Any]]:
    """SSE endpoint'i için: ("custom", {"delta": ...}) token parçalarını ve en
    sonda ("values", OrchestratorState) tam durumu sırayla yield eder."""
    async for mode, chunk in _compiled_graph.astream(
        _initial_state(user_id, session_id, message, history or []),
        stream_mode=["custom", "values"],
    ):
        yield mode, chunk
