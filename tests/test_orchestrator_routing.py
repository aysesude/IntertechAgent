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
        state = {
            "message": "Portföyümün değeri ne kadar?",
            "agent_responses": [_Response(True, summary_text="Portföy değeri 100 TL.")],
        }
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
        state = {
            "message": "Riskim nedir?",
            "agent_responses": [_Response(True, summary_text=text)],
        }
        result = await merge_responses(state, lambda chunk: None)
    finally:
        orch.get_llm_client = original

    assert result["final_answer"].count("Bu bir yatırım tavsiyesi değildir.") == 1


# ---------------------------------------------------------------------------
# Merge adımı soruyu görüyor mu
# ---------------------------------------------------------------------------


class _KaydedenLLM:
    """Kendisine ne verildiğini saklayan sahte istemci."""

    def __init__(self):
        self.prompt = None
        self.system = None

    async def generate(self, prompt, system=None):
        return ""

    async def stream(self, prompt, system=None):
        self.prompt = prompt
        self.system = system
        yield "cevap"


async def _merge_ile_calistir(state):
    import agents.orchestrator as orch

    llm = _KaydedenLLM()
    original = orch.get_llm_client
    orch.get_llm_client = lambda: llm
    try:
        await merge_responses(state, lambda chunk: None)
    finally:
        orch.get_llm_client = original
    return llm


async def test_user_question_reaches_the_merge_step():
    """Soru merge'e GEÇMELİ.

    Geçmediğinde model yalnızca veri yığınını görüyordu ve elinde soru
    olmadığı için yapabileceği tek şey her şeyi tekrar yazmaktı: "en çok
    kazandıran varlığım hangisi?" sorusuna sekiz varlık sıralanıp cevap en
    sona gömülüyordu (ölçüldü, 23 Ağustos test turu).
    """
    llm = await _merge_ile_calistir(
        {
            "message": "En çok kazandıran varlığım hangisi?",
            "agent_responses": [_Response(True, summary_text="APT +%28,28 | GARAN -%12,66")],
        }
    )

    assert "En çok kazandıran varlığım hangisi?" in llm.prompt
    # Soru, veriyle aynı bloğa karışmamalı: karışsaydı model onu da
    # aktarılacak veri sanabilirdi.
    assert "KULLANICININ SORUSU" in llm.prompt


async def test_merge_is_told_to_answer_the_question_not_restate_everything():
    """Talimat "her şeyi aktar"dan "soruyu cevapla"ya dönmüş olmalı.

    Eski prompt'taki "Hiçbir bilgiyi silme" cümlesi modeli eleme yapmaktan
    men ediyordu. Kural kaldırılmadı, ikiye ayrıldı: veri elenebilir,
    uyarılar elenemez.
    """
    llm = await _merge_ile_calistir(
        {"message": "Riskim nedir?", "agent_responses": [_Response(True, summary_text="x")]}
    )

    assert "Hiçbir bilgiyi silme" not in llm.system
    assert "İLGİSİZ VERİYİ DIŞARIDA BIRAK" in llm.system
    # Uyarı koruması hâlâ yerinde olmalı — asıl amacı buydu.
    assert "UYARILARI KORU" in llm.system
    # Uydurmama ve sorumluluk reddi pazarlıksız (CLAUDE.md §4).
    assert "VERİDE YOKSA SÖYLE" in llm.system
    assert "Bu bir yatırım tavsiyesi değildir." in llm.system


async def test_merge_survives_a_state_without_a_message():
    """Soru alanı eksikse cevap odağını kaybeder ama sohbet DÜŞMEZ.

    Burası nihai yanıtın yazıldığı yer; bir KeyError tüm yanıtı götürürdü.
    """
    llm = await _merge_ile_calistir({"agent_responses": [_Response(True, summary_text="veri")]})

    assert llm.prompt is not None
    assert "KULLANICININ SORUSU" not in llm.prompt


# ---------------------------------------------------------------------------
# Siniflandiricinin "hicbiri" secenekleri
# ---------------------------------------------------------------------------


class _PromptKaydeden(_FakeLLM):
    """Siniflandiriciya NE verildigini de saklar."""

    def __init__(self, reply: str = ""):
        super().__init__(reply)
        self.prompt = None
        self.system = None

    async def generate(self, prompt, system=None):
        self.prompt = prompt
        self.system = system
        return self._reply


async def test_kapsam_disi_etiketi_ajana_gitmez(monkeypatch):
    """Hava durumu sorusu RAG'e dusup "veritabaninda bulunamadi" DEMEMELI.

    Siniflandiricinin "hicbiri" secenegi yoktu; kapsam disi her soru
    MARKET'e dusuyor, oradan RAG'e gidiyor ve kullaniciya sistem arizaliymis
    gibi bir mesaj donuyordu (olculdu, 23 Agustos test turu).
    """
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("KAPSAM_DISI"))
    result = await detect_intent({"message": "Kayseri'de hava nasıl?", "history": []})

    assert result["intent"] == "OUT_OF_SCOPE"
    assert result["final_answer"], "kullaniciya gosterilecek bir metin olmali"
    assert "bulunamadı" not in result["final_answer"].lower()


async def test_gelecek_tahmini_ayri_bir_mesajla_reddedilir(monkeypatch):
    """Tahmin reddi, kapsam disi reddiyle AYNI SEY DEGIL.

    Soru finansal ve varlik kapsam icinde; reddedilen sey elimizde olmayan
    bir bilgiyi uretmek. "Bu konuda yardimci olamiyorum" demek soruyu
    anlamadigimizi ima ederdi.
    """
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("TAHMIN"))
    result = await detect_intent({"message": "2027'de dolar kaç TL olacak?", "history": []})

    assert result["intent"] == "FUTURE_PREDICTION"
    assert "tahmin" in result["final_answer"].lower()


async def test_tahmin_ve_kapsam_disi_erken_cikis_listesinde():
    """Erken cikis listesinde olmazlarsa ajanlara dagitilirlar."""
    assert _route_after_intent(_state("FUTURE_PREDICTION")) == ["handle_out_of_scope"]
    assert _route_after_intent(_state("OUT_OF_SCOPE")) == ["handle_out_of_scope"]


async def test_reddetme_etiketi_ajan_etiketini_yener(monkeypatch):
    """Model iki etiketi birden yazarsa reddetme kazanmali.

    Aksi halde "altin yukselecek mi" gibi bir soru hem TAHMIN hem MARKET
    alip piyasa ajanina gidebilir ve tahmin reddi hic gorunmezdi.
    """
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("TAHMIN, MARKET"))
    result = await detect_intent({"message": "altın yükselecek mi", "history": []})

    assert result["intent"] == "FUTURE_PREDICTION"


async def test_siniflandirici_sohbet_gecmisini_gorur(monkeypatch):
    """Takip sorusu, oncesine bakilmadan siniflandirilamaz.

    "Riskim nedir?" cevabinin ardindan gelen "Bunu biraz daha aciklar
    misin?" sorusu kendi basina hicbir konuya baglanamiyor ve AMBIGUOUS'a
    dusuyordu; kullanici "sorunuzu anlayamadim" cevabi aliyordu.
    """
    llm = _PromptKaydeden("RISK")
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: llm)

    await detect_intent(
        {
            "message": "Bunu biraz daha açıklar mısın?",
            "history": [
                {"role": "user", "content": "Riskim nedir?"},
                {"role": "assistant", "content": "Risk seviyeniz Çok Düşük."},
            ],
        }
    )

    assert "Riskim nedir?" in llm.prompt
    assert "ÖNCEKİ KONUŞMA" in llm.prompt
    assert "TAKİP SORUSU" in llm.system


async def test_gecmis_yoksa_yalnizca_soru_gonderilir(monkeypatch):
    """Ilk mesajda bos bir "onceki konusma" blogu gonderilmemeli."""
    llm = _PromptKaydeden("PORTFOLIO")
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: llm)

    await detect_intent({"message": "Portföyüm ne durumda?", "history": []})

    assert llm.prompt == "Portföyüm ne durumda?"


async def test_merge_kaynak_listesini_korumakla_gorevli():
    """Kaynak izlenebilirligi pazarliksiz (CLAUDE.md §4).

    Merge adimi metni yeniden yazarken RAG yanitlarinin "Kaynaklar:" blogunu
    dusurebiliyordu: ayni test turunda Akbank yaniti kaynak tasirken THYAO ve
    SPK yanitlari tasimiyordu. Kaynagi dusurmek bilgiyi dogrulanamaz yapar.
    """
    llm = await _merge_ile_calistir(
        {
            "message": "THYAO'nun son çeyrek sonuçları nasıldı?",
            "agent_responses": [_Response(True, summary_text="Net kâr 8,9 milyar TL.")],
        }
    )

    assert "KAYNAKLARI KORU" in llm.system


async def test_merge_turkce_bicim_kurali_tasiyor():
    """Ayni turda "%+8,21" gibi ters bicimler cikti; dogrusu "+%8,21"."""
    llm = await _merge_ile_calistir(
        {"message": "Kâr/zararım ne?", "agent_responses": [_Response(True, summary_text="x")]}
    )

    assert "+%8,41" in llm.system, "biçim örneği prompt'ta olmalı"
