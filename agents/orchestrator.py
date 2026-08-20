"""Orchestrator: kullanıcı isteğini alır, niyeti tespit eder, ilgili ajanlara
dağıtır, sonuçları birleştirip tek bir cevap üretir (LangGraph).

Graf yapısı:

    detect_intent ─┬─> handle_out_of_scope ─────────────> END
                   ├─> portfolio_agent ─┐
                   ├─> market_agent ────┼─> merge ─────> END
                   └─> risk_agent ──────┘

Niyet tespiti bir VEYA BİRDEN FAZLA hedef üretebilir (ör. "riskim nasıl ve son
haberler neler" → risk + piyasa); seçilen ajanlar **sırayla** çalışır.

Neden paralel değil de sıralı: her iki ajan da token akışı üretiyor. Paralel
çalıştırıldıklarında token'lar iç içe geçip okunamaz bir metin oluşuyor.
Sıralı çalıştırmak akışı bozmuyor; paralellik ancak akış birleştirme mantığı
yazılırsa anlamlı olur (TODO).

Ajan node'ları `writer: StreamWriter` parametresi alır: LangGraph tarafından
otomatik enjekte edilir, `stream_mode="custom"` kullanılmadığında no-op'tur —
böylece `run_orchestrator()` (tek seferlik) ve `stream_orchestrator()` (SSE)
aynı graf üzerinden çalışır.
"""

import logging
import operator
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import StreamWriter

from agents.base import AgentRequest, AgentResponse
from agents.market_agent import MarketAgent
from agents.portfolio_agent import PortfolioAgent
from agents.risk_agent import RiskAgent
from app.core.config import settings
from app.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# CLAUDE.md §4: her finansal çıktı bu uyarıyı taşımalı. Metni LLM'in eklemesine
# GÜVENİLMEZ (unutabilir, farklı yazabilir) — sunum katmanı olarak burada
# garanti altına alınır.
DISCLAIMER = "Bu bir yatırım tavsiyesi değildir."

SYSTEM_UNAVAILABLE_MESSAGE = "Şu an sistemlerimize ulaşılamıyor, lütfen daha sonra tekrar deneyin."


class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    message: str
    # Son N mesajlık sohbet geçmişi ({"role": ..., "content": ...} sözlükleri).
    # TODO: Ajanlar şu an bunu prompt'larına dahil etmiyor (tek turluk
    # çalışıyorlar); alan, çok turlu bağlam gereken ajanlar için hazır tutuluyor.
    history: list[dict[str, str]]
    # Loglanabilir tek satırlık niyet özeti ("portfolio, risk" gibi).
    intent: str
    # Çalıştırılacak node adları. Birden fazla olabilir.
    targets: list[str]
    agent_responses: Annotated[list[AgentResponse], operator.add]
    final_answer: str


_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Türkçe klavyesi olmayan / aksan girmeyen kullanıcı için "gonder" ile "gönder"
# aynı kelime sayılsın diye ASCII'ye katlanır (rag/retriever.py ile aynı desen).
_TURKISH_FOLD_MAP = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})

# Sistemin yetkisi olmayan işlem talepleri. Katlanmış (aksansız) yazılır.
_TRANSACTION_KEYWORDS = {
    "transfer",
    "havale",
    "eft",
    "gonder",
    "yolla",
    "satin",
    "al",
    "sat",
    "alim",
    "satim",
}

# Finans dışı sohbet. Katlanmış (aksansız) yazılır.
_OUT_OF_SCOPE_KEYWORDS = {"hava", "nasilsin", "kimsin", "sarki", "film", "yemek"}

_TRANSACTION_REFUSAL = (
    "Bu işlemi gerçekleştirmeye yetkim bulunmuyor. Yalnızca portföy durumunuzu, "
    "riskinizi ve piyasa haberlerini analiz edebilirim."
)
_OUT_OF_SCOPE_REFUSAL = (
    "Finansal danışmanınız olarak yalnızca portföyünüz ve finansal piyasalar "
    "hakkındaki sorularınızı yanıtlayabilirim.\n\nÖrnek sorular:\n"
    "- Portföyüm ne durumda?\n- Riskim yüksek mi?\n- Son piyasa haberleri neler?"
)


def _tokens(text: str) -> set[str]:
    """Sorguyu kelimelere böler.

    Neden alt dizi (`"al" in query`) değil de kelime: alt dizi araması
    "portföy an**al**izi", "**al**tın ne durumda" ve "**hava**cılık hisseleri"
    gibi tamamen meşru soruları işlem talebi/kapsam dışı sayıp reddediyordu
    (ölçümle doğrulandı). Kelime bazlı eşleşmede "analiz" ile "al" farklı iki
    kelimedir.

    Bilinen ödünleşme: çekim eki almış biçimler ("alabilir miyim", "satmalı
    mıyım") artık yakalanmaz ve soru ajana gider. Bu yön kasıtlı seçildi —
    meşru bir soruyu reddetmek, kapsam dışı bir soruyu ajana göndermekten
    daha maliyetli.

    Türkçe büyük "İ" düz `lower()`'da birleşen nokta işaretine ayrıldığı için
    (bkz. rag/retriever.py) önce sadeleştirilir.
    """
    normalized = text.replace("İ", "i").lower().translate(_TURKISH_FOLD_MAP)
    return set(_WORD_RE.findall(normalized))


# LLM'in döndürebileceği etiket -> çalıştırılacak graf node'u.
_INTENT_TARGETS: dict[str, str] = {
    "PORTFOLIO": "portfolio_agent",
    "MARKET": "market_agent",
    "RISK": "risk_agent",
}

_INTENT_SYSTEM_PROMPT = (
    "Sen bir niyet sınıflandırma motorusun. Kullanıcının sorusunu aşağıdaki "
    "etiketlerden bir veya birkaçına ata. SADECE etiketleri, virgülle ayırarak, "
    "büyük harfle yaz. Açıklama, cümle veya noktalama ekleme.\n"
    "- PORTFOLIO: kullanıcının kendi varlıkları, portföy değeri, dağılımı, kâr/zarar durumu.\n"
    "- MARKET: piyasa haberleri, şirket bilançoları, döviz kurları, faiz oranları, "
    "hisse fiyatları — kullanıcının dışındaki dünya.\n"
    "- RISK: kullanıcının portföyünün riski, volatilitesi, ne kadar riskli olduğu, "
    "yeniden dengeleme veya strateji önerisi.\n"
    "Örnekler:\n"
    "Portföyüm ne durumda? -> PORTFOLIO\n"
    "Son piyasa haberleri neler? -> MARKET\n"
    "Riskim yüksek mi? -> RISK\n"
    "Portföyümü nasıl dengelerim? -> RISK\n"
    "Portföyüm ne durumda ve son haberler neler? -> PORTFOLIO, MARKET\n"
    "Aselsan bilançosu portföyümü nasıl etkiler? -> PORTFOLIO, MARKET"
)


def _parse_targets(response_text: str) -> list[str]:
    """LLM yanıtındaki etiketleri graf node adlarına çevirir.

    Yanıt serbest metin olabilir (küçük modeller "Cevap: PORTFOLIO" gibi
    yazabiliyor), o yüzden etiketler metnin içinde aranır. `_INTENT_TARGETS`
    sırası korunur ki aynı niyet kümesi her zaman aynı sırada çalışsın
    (determinizm).
    """
    upper = response_text.upper()
    # Geriye dönük uyum: önceki sürüm portföy+piyasa için tek kelime "BOTH"
    # dönüyordu; eski bir modelin/prompt kalıntısının bunu üretmesi hâlinde
    # cevapsız kalmasın.
    if "BOTH" in upper:
        return ["portfolio_agent", "market_agent"]
    return [node for label, node in _INTENT_TARGETS.items() if label in upper]


async def detect_intent(state: OrchestratorState) -> dict:
    """Kullanıcının niyetini LLM yardımıyla sınıflandırır. Kapsam dışı sorular baştan reddedilir."""
    query = state["message"].strip()
    query_tokens = _tokens(query)

    # 1. Kural tabanlı kapsam kontrolü (scope guard) — LLM'e hiç gitmeden.
    if query_tokens & _TRANSACTION_KEYWORDS:
        return {
            "intent": "out_of_scope",
            "targets": ["handle_out_of_scope"],
            "final_answer": _TRANSACTION_REFUSAL,
        }

    if query_tokens & _OUT_OF_SCOPE_KEYWORDS:
        return {
            "intent": "out_of_scope",
            "targets": ["handle_out_of_scope"],
            "final_answer": _OUT_OF_SCOPE_REFUSAL,
        }

    # 2. LLM tabanlı niyet tespiti
    llm = get_llm_client()
    try:
        response = await llm.generate(query, system=_INTENT_SYSTEM_PROMPT)
        targets = _parse_targets(response)
    except Exception as e:
        logger.error("[ORCHESTRATOR] Niyet tespiti LLM hatasi: %s", e)
        targets = []

    if not targets:
        # Hiçbir etiket tanınmadıysa (LLM hatası ya da beklenmedik yanıt)
        # portföy ajanına düşülür: kullanıcının kendi verisi her zaman
        # elimizde, yani en az bir anlamlı cevap üretilebilir.
        targets = ["portfolio_agent"]

    intent = ", ".join(targets)
    logger.info("[ORCHESTRATOR] Niyet tespiti: %s | sorgu=%r", intent, state["message"][:80])
    return {"intent": intent, "targets": targets}


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


async def run_risk_agent(state: OrchestratorState) -> dict:
    agent = RiskAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def handle_out_of_scope(state: OrchestratorState, writer: StreamWriter) -> dict:
    """Kapsam dışı durumlarda LLM'e gitmeden doğrudan uyarı mesajını akıtır."""
    # Metni kelime kelime akıtarak animasyonlu hissi ver
    words = state["final_answer"].split(" ")
    for i, word in enumerate(words):
        writer({"delta": word + (" " if i < len(words) - 1 else "")})
    return {}


def _with_disclaimer(text: str) -> str:
    """Uyarıyı ekler; metin zaten taşıyorsa iki kez yazmaz."""
    if DISCLAIMER.lower() in text.lower():
        return text
    return f"{text}\n\n{DISCLAIMER}"


def _unique(items: list[str]) -> list[str]:
    """Sırayı bozmadan tekrarları atar (iki ajan aynı hata metnini dönebilir)."""
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


_MERGE_SYSTEM_PROMPT = (
    "Aşağıda birden fazla uzman ajandan gelen ham yanıtlar ve varsa eksik bilgiler bulunmaktadır.\n"
    "Görev: Bu verileri alıp, objektif, pürüzsüz, tekil ve anlaşılır bir Türkçe yanıt oluşturarak "
    "son kullanıcıya sun.\n"
    "Verilerin hangi ajandan geldiğini söyleme, doğrudan bilgiyi harmanlayıp ver.\n"
    "Eğer bazı bilgiler eksikse ('ALINAMAYAN BİLGİLER' kısmı varsa), bunu kullanıcıya doğal bir "
    "dille ('Şu an piyasa verilerine ulaşamıyorum ancak portföyünüz...' gibi) belirt.\n"
    "Hiçbir sayıyı değiştirme, hiçbir bilgiyi silme, kendinden bilgi ekleme — sadece metinleri "
    "iyi bir düzene sok.\n"
    "Yanıtına 'Merhaba', 'Cevap:' gibi etiketler ekleme. Sadece içeriği ver.\n"
    f"Yanıtının en sonuna '{DISCLAIMER}' uyarısını ekle."
)


async def merge_responses(state: OrchestratorState, writer: StreamWriter) -> dict:
    """Ajan yanıtlarını tek bir cevaba indirger ve akıtır.

    Üç yol var; hepsinin ortak sözü: bu node'dan kullanıcıya **her zaman** en az
    bir delta gider. Eskiden gitmeyebiliyordu — merge LLM'i istisna atmadan boş
    yanıt döndürdüğünde ne token ne hata üretiliyordu ve arayüzde boş bir balon
    kalıyordu (üretimde gözlendi). Aşağıdaki her dal bir metin yazar.
    """
    successful = _unique(
        [
            r.summary_text.strip()
            for r in state["agent_responses"]
            if r.success and r.summary_text.strip()
        ]
    )
    errors = _unique([r.error for r in state["agent_responses"] if r.error])

    # 1) Kullanılabilir hiçbir metin yok. Tool'ların hata mesajları kullanıcıya
    # gösterilmek üzere yazılmıştır (bkz. mcp_server/tools/_base.py
    # DEFAULT_MESSAGES), o yüzden genel bir "sistem hatası" metniyle
    # değiştirilmez: "bu sorguyla ilgili doğrulanmış bilgi bulunamadı" demek,
    # "sistemlerimize ulaşılamıyor" demekten hem doğru hem yararlıdır.
    if not successful:
        final_answer = _with_disclaimer(
            "\n\n".join(errors) if errors else SYSTEM_UNAVAILABLE_MESSAGE
        )
        writer({"delta": final_answer})
        return {"final_answer": final_answer}

    # 2) Tek kaynak, eksik bilgi yok: birleştirilecek bir şey yok. Ajanın metni
    # zaten Türkçe ve kullanıcıya hazır; ikinci bir LLM turu ne bilgi ekler ne
    # biçim düzeltir — yalnızca gecikme (5 sn hedefi, CLAUDE.md §3 A5) ve bir
    # kırılma noktası ekler.
    if len(successful) == 1 and not errors:
        final_answer = _with_disclaimer(successful[0])
        writer({"delta": final_answer})
        return {"final_answer": final_answer}

    # 3) Birden fazla kaynak ya da kısmi başarı: LLM ile tek metne indir.
    combined_texts = ["BAŞARILI BİLGİLER:\n" + "\n\n---\n\n".join(successful)]
    if errors:
        combined_texts.append("ALINAMAYAN BİLGİLER (KULLANICIYA BELİRT):\n" + "\n".join(errors))
    combined_text = "\n\n".join(combined_texts)

    merged = ""
    try:
        async for chunk in get_llm_client().stream(combined_text, system=_MERGE_SYSTEM_PROMPT):
            merged += chunk
            writer({"delta": chunk})
    except Exception as e:
        logger.error("[ORCHESTRATOR] Merge LLM hatasi: %s", e)

    if not merged.strip():
        # LLM ya istisna attı ya da hiç parça üretmedi. İkisinde de elimizdeki
        # ham metinlere düşülür: birleştirilmemiş ama doğru bir cevap, boş
        # ekrandan iyidir.
        final_answer = _with_disclaimer("\n\n".join(successful + errors))
        writer({"delta": final_answer})
        return {"final_answer": final_answer}

    # Akış yarıda kesilmiş olabilir; uyarı eksikse yalnızca eklenen kuyruk
    # akıtılır (baştan yazmak metni ikizlerdi).
    final_answer = _with_disclaimer(merged)
    tail = final_answer[len(merged) :]
    if tail:
        writer({"delta": tail})
    return {"final_answer": final_answer}


def _route_after_intent(state: OrchestratorState) -> list[str]:
    """Niyet tespitinin seçtiği node'lara dağıtır."""
    return state["targets"] or ["portfolio_agent"]


def _build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("detect_intent", detect_intent)
    graph.add_node("handle_out_of_scope", handle_out_of_scope)
    graph.add_node("portfolio_agent", run_portfolio_agent)
    graph.add_node("market_agent", run_market_agent)
    graph.add_node("risk_agent", run_risk_agent)
    graph.add_node("merge", merge_responses)

    graph.set_entry_point("detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        _route_after_intent,
        {
            "handle_out_of_scope": "handle_out_of_scope",
            "portfolio_agent": "portfolio_agent",
            "market_agent": "market_agent",
            "risk_agent": "risk_agent",
        },
    )

    graph.add_edge("handle_out_of_scope", END)
    graph.add_edge("portfolio_agent", "merge")
    graph.add_edge("market_agent", "merge")
    graph.add_edge("risk_agent", "merge")
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
        "targets": [],
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
