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

import logging
import operator
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import StreamWriter

from agents.base import AgentRequest, AgentResponse
from agents.market_agent import MarketAgent
from agents.portfolio_agent import PortfolioAgent
from app.core.config import settings
from app.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)


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


async def detect_intent(state: OrchestratorState) -> dict:
    """Kullanıcının niyetini LLM yardımıyla sınıflandırır. Kapsam dışı sorular baştan reddedilir."""
    query = state["message"].strip()
    query_lower = query.lower()

    # 1. Kural Tabanlı Kapsam Kontrolü (Scope Guard)
    transaction_keywords = {"transfer", "gönder", "yolla", "al", "sat", "alım", "satım"}
    if any(k in query_lower for k in transaction_keywords):
        return {
            "intent": "out_of_scope",
            "final_answer": "Bu işlemi gerçekleştirmeye yetkim bulunmuyor. Yalnızca portföy durumunuzu ve piyasa haberlerini analiz edebilirim.",
        }

    out_of_scope_keywords = {"hava", "nasılsın", "kimsin", "şarkı", "film", "yemek"}
    if any(k in query_lower for k in out_of_scope_keywords):
        return {
            "intent": "out_of_scope",
            "final_answer": "Finansal danışmanınız olarak yalnızca portföyünüz ve finansal piyasalar hakkındaki sorularınızı yanıtlayabilirim.\n\nÖrnek sorular:\n- Portföyüm ne durumda?\n- Son piyasa haberleri neler?",
        }

    # 2. LLM Tabanlı Niyet Tespiti
    llm = get_llm_client()
    system_prompt = (
        "Sen bir niyet sınıflandırma motorusun. SADECE tek kelime çıktı vereceksin: PORTFOLIO, MARKET veya BOTH.\n"
        "- Eğer kullanıcı kendi varlıklarını, portföyünü, yatırımlarını veya parasının durumunu soruyorsa: PORTFOLIO dön.\n"
        "- Eğer kullanıcı piyasa haberlerini, şirket bilançolarını, kurları, faiz oranlarını veya hisse fiyatlarını soruyorsa: MARKET dön.\n"
        "- Eğer kullanıcı her ikisini de aynı anda soruyorsa (örneğin 'Portföyüm ne durumda ve son haberler neler?'): BOTH dön.\n"
        "Asla açıklama yapma, sadece kategori adını büyük harfle döndür."
    )

    try:
        response = await llm.generate(query, system=system_prompt)
        response_text = response.strip().upper()

        if "BOTH" in response_text:
            intent = "both"
        elif "MARKET" in response_text or "RAG" in response_text:
            intent = "market"
        else:
            intent = "portfolio"  # Varsayılan (fallback) değer

    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Niyet tespiti LLM hatası: {e}")
        intent = "portfolio"

    logger.info(
        "[ORCHESTRATOR] LLM niyet tespiti: %s | sorgu=%r",
        intent,
        state["message"][:80],
    )
    return {"intent": intent}


def _build_request(state: OrchestratorState) -> AgentRequest:
    return AgentRequest(
        user_id=state["user_id"],
        session_id=state["session_id"],
        query=state["message"],
        context={"recent_messages": state["history"]},
    )


async def run_portfolio_agent(state: OrchestratorState) -> dict:
    agent = PortfolioAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def run_market_agent(state: OrchestratorState) -> dict:
    agent = MarketAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def handle_out_of_scope(state: OrchestratorState, writer: StreamWriter) -> dict:
    """Kapsam dışı durumlarda LLM'e gitmeden doğrudan uyarı mesajını akıtır."""
    # Metni kelime kelime akıtarak animasyonlu hissi ver
    words = state["final_answer"].split(" ")
    for i, word in enumerate(words):
        writer({"delta": word + (" " if i < len(words) - 1 else "")})
    return {}


async def merge_responses(state: OrchestratorState, writer: StreamWriter) -> dict:
    successful = [r.summary_text for r in state["agent_responses"] if r.success]
    errors = [r.error for r in state["agent_responses"] if r.error]

    # Hiçbir ajan başarılı olmadıysa (İç Hata Gizliliği)
    if not successful:
        final_answer = "Şu an sistemlerimize ulaşılamıyor, lütfen daha sonra tekrar deneyin."
        writer({"delta": final_answer})
        return {"final_answer": final_answer}

    llm = get_llm_client()

    # Kısmi veya tam başarı durumu
    combined_texts = []
    if successful:
        combined_texts.append("BAŞARILI BİLGİLER:\n" + "\n\n---\n\n".join(successful))
    if errors:
        combined_texts.append("ALINAMAYAN BİLGİLER (KULLANICIYA BELİRT):\n" + "\n".join(errors))

    combined_text = "\n\n".join(combined_texts)

    system_prompt = (
        "Aşağıda bir veya daha fazla veri kaynağından/uzman ajandan gelen ham yanıtlar ve varsa eksik bilgiler bulunmaktadır.\n"
        "Görev: Bu verileri alıp, objektif, pürüzsüz, tekil ve anlaşılır bir Türkçe yanıt oluşturarak son kullanıcıya sun.\n"
        "Verilerin hangi ajan veya RAG'den geldiğini söyleme, doğrudan bilgiyi harmanlayıp ver.\n"
        "Eğer bazı bilgiler eksikse ('ALINAMAYAN BİLGİLER' kısmı varsa), bunu kullanıcıya doğal bir dille ('Şu an piyasa verilerine ulaşamıyorum ancak portföyünüz...' gibi) belirt.\n"
        "Hiçbir bilgiyi silme veya uydurma yapma, sadece metinleri iyi bir düzene sok.\n"
        "Yanıtına 'Merhaba', 'Cevap:' gibi etiketler ekleme. Sadece içeriği ver.\n"
        "ÖNEMLİ: Her yanıtının en sonuna mutlaka 'Bu bir yatırım tavsiyesi değildir.' uyarısını ekle."
    )

    final_answer = ""
    try:
        async for chunk in llm.stream(combined_text, system=system_prompt):
            final_answer += chunk
            writer({"delta": chunk})
    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Merge LLM hatası: {e}")
        final_answer = "\n\n".join(successful) + "\n\nBu bir yatırım tavsiyesi değildir."
        writer({"delta": final_answer})

    return {"final_answer": final_answer}


def _route_after_intent(state: OrchestratorState) -> list[str]:
    """Niyete göre ilgili ajanlara paralel dağıtım yapar veya kapsam dışı akışına yönlendirir."""
    if state["intent"] == "out_of_scope":
        return ["handle_out_of_scope"]
    if state["intent"] == "both":
        return ["portfolio_agent", "market_agent"]
    if state["intent"] == "market":
        return ["market_agent"]
    return ["portfolio_agent"]


def _build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("detect_intent", detect_intent)
    graph.add_node("handle_out_of_scope", handle_out_of_scope)
    graph.add_node("portfolio_agent", run_portfolio_agent)
    graph.add_node("market_agent", run_market_agent)
    graph.add_node("merge", merge_responses)

    graph.set_entry_point("detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        _route_after_intent,
        {
            "handle_out_of_scope": "handle_out_of_scope",
            "portfolio_agent": "portfolio_agent",
            "market_agent": "market_agent",
        },
    )

    graph.add_edge("handle_out_of_scope", END)
    graph.add_edge("portfolio_agent", "merge")
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
