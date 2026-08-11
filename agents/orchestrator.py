"""Orchestrator: kullanıcı isteğini alır, niyeti tespit eder, ilgili ajanlara
dağıtır, sonuçları birleştirip tek bir cevap üretir (LangGraph).

Bu aşamada tek ajan (Portföy Ajanı) bağlı; `agent_responses` alanı Market/Risk
ajanları eklendiğinde paralel node'ların sonuçlarını biriktirebilsin diye
`operator.add` reducer'ı ile tanımlandı.

`run_portfolio_agent` node'u `writer: StreamWriter` parametresi alır: bu,
LangGraph tarafından otomatik enjekte edilir, `stream_mode="custom"`
kullanılmadığında no-op'tur — yani `run_orchestrator()` (tek seferlik) ve
`stream_orchestrator()` (SSE) aynı graf üzerinden çalışır, kod tekrarı yok."""

import operator
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from app.core.config import settings
from langgraph.graph import END, StateGraph
from langgraph.types import StreamWriter

from agents.base import AgentRequest, AgentResponse
from agents.portfolio_agent import PortfolioAgent


class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    message: str
    # Son N mesajlık sohbet geçmişi ({"role": ..., "content": ...} sözlükleri).
    # TODO: PortfolioAgent şu an bunu prompt'una dahil etmiyor (tek turluk
    # çalışıyor); alan, çok turlu bağlam gereken ajanlar için hazır tutuluyor.
    history: list[dict[str, str]]
    intent: str
    agent_responses: Annotated[list[AgentResponse], operator.add]
    final_answer: str


def detect_intent(state: OrchestratorState) -> dict:
    # TODO: gerçek niyet tespiti (kural tabanlı veya LLM ile) eklenecek. Şu an
    # tek ajan bağlı olduğu için niyet sabit "portfolio".
    return {"intent": "portfolio"}


async def run_portfolio_agent(state: OrchestratorState, writer: StreamWriter) -> dict:
    agent = PortfolioAgent(mcp_server_url=settings.mcp_server_url)
    request = AgentRequest(
        user_id=state["user_id"],
        session_id=state["session_id"],
        query=state["message"],
        context={"recent_messages": state["history"]},
    )
    response = await agent.execute(request, on_token=lambda token: writer({"delta": token}))
    return {"agent_responses": [response]}


def merge_responses(state: OrchestratorState) -> dict:
    successful = [r.summary_text for r in state["agent_responses"] if r.success]
    if successful:
        final_answer = "\n\n".join(successful)
    else:
        errors = [r.error for r in state["agent_responses"] if r.error]
        final_answer = errors[0] if errors else "Üzgünüm, isteğinizi işlerken bir sorun oluştu."
    return {"final_answer": final_answer}


def _build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("detect_intent", detect_intent)
    graph.add_node("portfolio_agent", run_portfolio_agent)
    graph.add_node("merge", merge_responses)
    graph.set_entry_point("detect_intent")
    graph.add_edge("detect_intent", "portfolio_agent")
    graph.add_edge("portfolio_agent", "merge")
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
    return await _compiled_graph.ainvoke(_initial_state(user_id, session_id, message, history or []))


async def stream_orchestrator(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]] | None = None
) -> AsyncIterator[tuple[str, Any]]:
    """SSE endpoint'i için: ("custom", {"delta": ...}) token parçalarını ve en
    sonda ("values", OrchestratorState) tam durumu sırayla yield eder."""
    async for mode, chunk in _compiled_graph.astream(
        _initial_state(user_id, session_id, message, history or []), stream_mode=["custom", "values"]
    ):
        yield mode, chunk
