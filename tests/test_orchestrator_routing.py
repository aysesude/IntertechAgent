"""Orchestrator niyet tespiti ve yönlendirme — FR-4 / US-02.

Buradaki her test canlı ortamda ölçülmüş bir davranışa karşılık geliyor:
"riskim nedir" sorusu risk ajanı yerine portföy ajanına düşüyor ve kullanıcı
risk değerlendirmesi aldığını sanarak portföy özeti okuyordu.
"""

import pytest

from agents.orchestrator import (
    _AMBIGUOUS_MESSAGE,
    AGENT_INTENTS,
    AGENT_NODES,
    _build_graph,
    _route_after_intent,
    detect_intent,
    merge_responses,
)


class _FakeLLM:
    """`generate` sabit metin döndürür; `stream` tek parça akıtır."""

    def __init__(self, reply: str = "", *, raises: bool = False):
        self._reply = reply
        self._raises = raises

    async def generate(self, prompt, system=None):
        if self._raises:
            raise RuntimeError("LLM düştü")
        return self._reply

    async def stream(self, prompt, system=None):
        if self._raises:
            raise RuntimeError("LLM düştü")
        yield self._reply


def _state(intent: str) -> dict:
    return {"intent": intent, "final_answer": ""}


# --------------------------------------------------------------------------
# Yönlendirme
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent,expected",
    [
        ("portfolio", ["portfolio_agent"]),
        ("market", ["market_agent"]),
        ("risk", ["risk_agent"]),
        ("portfolio+risk", ["portfolio_agent", "risk_agent"]),
        ("market+risk", ["market_agent", "risk_agent"]),
        ("portfolio+market", ["portfolio_agent", "market_agent"]),
        # Eski tek kelimelik etiket geriye dönük tanınmalı.
        ("both", ["portfolio_agent", "market_agent"]),
    ],
)
def test_intent_routes_to_expected_agents(intent, expected):
    assert _route_after_intent(_state(intent)) == expected


@pytest.mark.parametrize(
    "intent",
    ["AMBIGUOUS", "OUT_OF_SCOPE", "UNAUTHORIZED_ACTION", "INJECTION_ATTEMPT", "SYSTEM_INFO"],
)
def test_early_exit_intents_skip_agents(intent):
    assert _route_after_intent(_state(intent)) == ["handle_out_of_scope"]


def test_unknown_intent_asks_instead_of_defaulting_to_portfolio():
    """Tanınmayan etiket sessizce portföye düşmemeli.

    Regresyon: `_route_after_intent` koşulsuz `["portfolio_agent"]` dönüyordu.
    Niyet tespiti RISK etiketi üretemediği için risk soruları buraya düşüyor,
    kullanıcı risk değerlendirmesi yerine portföy özeti alıyor ve bunu cevap
    sanıyordu (CLAUDE.md §4 uydurmama).
    """
    state = _state("beklenmeyen_etiket")
    assert _route_after_intent(state) == ["handle_out_of_scope"]


def test_ambiguous_message_mentions_risk_as_an_example():
    """Kullanıcı risk sorabileceğini bilmeli."""
    assert "isk" in _AMBIGUOUS_MESSAGE


# --------------------------------------------------------------------------
# Niyet tespiti (LLM taklidi)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "llm_reply,expected",
    [
        ("RISK", "risk"),
        ("PORTFOLIO", "portfolio"),
        ("MARKET", "market"),
        ("PORTFOLIO, RISK", "portfolio+risk"),
        ("MARKET, RISK", "market+risk"),
        ("PORTFOLIO, MARKET", "portfolio+market"),
        # Eski prompt'un çıktıları geriye dönük tanınmalı.
        ("BOTH", "portfolio+market"),
        ("RAG", "market"),
        # Model saçmaladıysa uydurma yapılmaz, soru sorulur.
        ("bilmiyorum", "AMBIGUOUS"),
        ("", "AMBIGUOUS"),
    ],
)
async def test_detect_intent_parses_labels(monkeypatch, llm_reply, expected):
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM(llm_reply))
    result = await detect_intent({"message": "portföyüm ne durumda", "history": []})
    assert result["intent"] == expected


async def test_detect_intent_falls_back_when_llm_fails(monkeypatch):
    """LLM hatası çökmeye değil, açık bir soruya dönüşmeli (zarif düşüş)."""
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM(raises=True))
    result = await detect_intent({"message": "riskim nedir", "history": []})
    assert result["intent"] == "AMBIGUOUS"


async def test_scope_filter_short_circuits_before_llm(monkeypatch):
    """Kapsam kontrolü yakalarsa LLM'e hiç gidilmez."""

    def _boom():
        raise AssertionError("kapsam dışı soruda LLM çağrılmamalı")

    monkeypatch.setattr("agents.orchestrator.get_llm_client", _boom)
    result = await detect_intent({"message": "hisse al", "history": []})
    assert result["intent"] == "UNAUTHORIZED_ACTION"


# --------------------------------------------------------------------------
# Hata mesajı ayrımı
# --------------------------------------------------------------------------


class _Response:
    def __init__(self, success: bool, summary_text: str = "", error: str | None = None):
        self.success = success
        self.summary_text = summary_text
        self.error = error


async def test_tool_error_message_is_shown_instead_of_system_failure():
    """ "Kayıt bulunamadı" ile "sisteme ulaşılamıyor" aynı şey değil.

    Regresyon: RAG'de doküman bulunamadığında (NOT_FOUND) kullanıcıya
    "Şu an sistemlerimize ulaşılamıyor" gösteriliyordu — ayakta olan sistem
    çökmüş gibi sunuluyordu. Ölçüldü: "altın ne durumda", "dolar kuru ne
    durumda".
    """
    written: list[str] = []
    state = {
        "agent_responses": [_Response(False, error="İstenen kayıt bulunamadı.")],
    }
    result = await merge_responses(state, lambda chunk: written.append(chunk["delta"]))

    assert result["final_answer"] == "İstenen kayıt bulunamadı."
    assert "sistemlerimize ulaşılamıyor" not in result["final_answer"]
    assert written, "hata durumunda da en az bir parça akıtılmalı"


async def test_generic_message_when_no_error_text_available():
    """Ajan hata metni bırakmadıysa genel mesaj kalır (iç detay sızmaz)."""
    state = {"agent_responses": [_Response(False)]}
    result = await merge_responses(state, lambda chunk: None)
    assert "sistemlerimize ulaşılamıyor" in result["final_answer"]


async def test_duplicate_error_messages_are_not_repeated():
    """İki ajan aynı hataya düşerse metin iki kez yazılmaz."""
    state = {
        "agent_responses": [
            _Response(False, error="İstenen kayıt bulunamadı."),
            _Response(False, error="İstenen kayıt bulunamadı."),
        ],
    }
    result = await merge_responses(state, lambda chunk: None)
    assert result["final_answer"].count("İstenen kayıt bulunamadı.") == 1


# --------------------------------------------------------------------------
# Graf
# --------------------------------------------------------------------------


def test_graph_contains_all_three_agents():
    """Risk düğümü grafa gerçekten bağlanmış olmalı."""
    nodes = set(_build_graph().nodes)
    for node in AGENT_NODES.values():
        assert node in nodes, f"{node} grafta yok"


def test_agent_intents_and_nodes_are_in_sync():
    """Etiket eklenip düğüm eklenmemesi sessiz bir yönlendirme kaybı olurdu."""
    assert set(AGENT_INTENTS) == set(AGENT_NODES)


async def test_empty_llm_stream_does_not_leave_an_empty_bubble():
    """`stream` istisna atmadan hiç parça üretmezse ekranda boş balon kalıyordu.

    Eski `except` yalnızca istisnayı yakalıyordu; sessizce boş dönen bir akış
    `final_answer`'ı boş bırakıyor, writer hiç çağrılmıyor ve SSE'de ne token
    ne error olayı gidiyordu.
    """

    class _SilentLLM:
        async def generate(self, prompt, system=None):
            return ""

        async def stream(self, prompt, system=None):
            return
            yield  # pragma: no cover - üretici yapmak için

    import agents.orchestrator as orch

    original = orch.get_llm_client
    orch.get_llm_client = lambda: _SilentLLM()
    try:
        written: list[str] = []
        state = {"agent_responses": [_Response(True, summary_text="Portföy değeri 100 TL.")]}
        result = await merge_responses(state, lambda chunk: written.append(chunk["delta"]))
    finally:
        orch.get_llm_client = original

    assert "Portföy değeri 100 TL." in result["final_answer"]
    assert "Bu bir yatırım tavsiyesi değildir." in result["final_answer"]
    assert written, "boş akışta da kullanıcıya bir şey gitmeli"


async def test_disclaimer_is_not_duplicated_on_fallback():
    """Ajan metni uyarıyı zaten taşıyorsa ikilenmez."""

    class _SilentLLM:
        async def stream(self, prompt, system=None):
            return
            yield  # pragma: no cover

    import agents.orchestrator as orch

    original = orch.get_llm_client
    orch.get_llm_client = lambda: _SilentLLM()
    try:
        text = "Risk seviyeniz Orta. Bu bir yatırım tavsiyesi değildir."
        state = {"agent_responses": [_Response(True, summary_text=text)]}
        result = await merge_responses(state, lambda chunk: None)
    finally:
        orch.get_llm_client = original

    assert result["final_answer"].count("Bu bir yatırım tavsiyesi değildir.") == 1
