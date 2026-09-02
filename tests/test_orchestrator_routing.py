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
    _ayikla_korunan_bloklar,
    _build_graph,
    _kaynak_takip_yaniti,
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
        ("web_research", ["web_research_agent"]),
        # Kavram sorusu portföy sorusuyla birlikte gelebilir.
        ("portfolio+web_research", ["portfolio_agent", "web_research_agent"]),
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
        ("WEB_RESEARCH", "web_research"),
        ("PORTFOLIO, WEB_RESEARCH", "portfolio+web_research"),
        # WEB_RESEARCH içinde MARKET/RISK geçmiyor: etiket eşleşmesi alt dize
        # araması olduğu için yeni etiket eskileri tetiklememeli.
        # Eski prompt'un çıktıları geriye dönük tanınmalı.
        ("BOTH", "portfolio+market"),
        ("RAG", "market"),
        # Model saçmaladıysa uydurma yapılmaz, soru sorulur.
        ("bilmiyorum", "AMBIGUOUS"),
        ("", "AMBIGUOUS"),
    ],
)
async def test_detect_intent_parses_labels(monkeypatch, llm_reply, expected):
    # "portföy" KÖKÜ BİLEREK YOK: bu test saf etiket-ayrıştırmasını sınıyor,
    # 2026-08-27'de eklenen deterministik portföy güvencesi (aşağıdaki
    # `test_portfoy_ifadesi_*` testleri) burada karışmasın diye "ASELSAN
    # hakkında bilgi ver" kullanılıyor.
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM(llm_reply))
    result = await detect_intent({"message": "ASELSAN hakkında bilgi ver", "history": []})
    assert result["intent"] == expected


async def test_portfoy_ifadesi_llm_kacirsa_bile_etiketlenir(monkeypatch):
    """2026-08-27, analist test turu, ölçüldü: "Portföyümdeki X şirketinin
    son çeyrek gelir tablosunda dikkat çeken bir şey var mı" sorusu LLM
    tarafından yalnızca MARKET etiketlenmiş, PORTFOLIO kaçmıştı —
    portfolio_agent hiç çalışmadan market_agent, kullanıcının GERÇEK
    holdings'ini hiç bilmeden portföyde OLMAYAN şirketler hakkında cevap
    üretti (bkz. agents/market_query.py::portfoy_referansi_var_mi)."""
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("MARKET"))
    result = await detect_intent(
        {"message": "Portföyümdeki şirketlerin son çeyreği nasıldı", "history": []}
    )
    assert result["intent"] == "market+portfolio"


async def test_portfoy_ifadesi_zaten_etiketliyse_tekrarlanmaz(monkeypatch):
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("PORTFOLIO, MARKET"))
    result = await detect_intent(
        {"message": "Portföyümdeki şirketlerin son çeyreği nasıldı", "history": []}
    )
    assert result["intent"] == "portfolio+market"


async def test_portfoy_ifadesi_llm_sacmalarsa_bile_ambiguousa_dusmez(monkeypatch):
    """Model hiç anlamlı etiket üretmezse eskiden AMBIGUOUS'a düşüyordu;
    sorgu "portföyüm" gibi açık bir ifade taşıyorsa artık portfolio_agent'a
    yönlenir — kullanıcı en azından gerçek holdings'ini görür."""
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("bilmiyorum"))
    result = await detect_intent({"message": "portföyümde neler var", "history": []})
    assert result["intent"] == "portfolio"


async def test_portfoy_kelimesi_gecmeyen_sorguda_eski_davranis_korunur(monkeypatch):
    monkeypatch.setattr("agents.orchestrator.get_llm_client", lambda: _FakeLLM("MARKET"))
    result = await detect_intent({"message": "ASELSAN'ın son çeyreği nasıldı", "history": []})
    assert result["intent"] == "market"


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


def test_graph_contains_every_registered_agent():
    """Etiketi olan her ajanın grafta bir düğümü olmalı.

    Adı eskiden `..._all_three_agents` idi; ajan sayısı arttıkça adın
    güncellenmesi unutuluyor, oysa test zaten AGENT_NODES üzerinden geziyor.
    """
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
    assert written, "boş akışta da kullanıcıya bir şey gitmeli"


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


# ---------------------------------------------------------------------------
# Korunan kuyruk bloklari (2026-08-31, ikinci tur)
#
# "Varlık bazlı gözlemler" ve "Risk profili uyumu" bloklari eskiden yalnizca
# sistem promptunda "AYNEN koru" talimatiyla LLM'e gosteriliyordu. Canli
# arayuz testinde ikisi de basarisiz oldu: ilkinde LLM basligi ve maddeleri
# dusurup yalnizca kapanis cumlesini birakti; ikincisi hic korunmadigi icin
# LLM onu SINIF duzeyine geri yorumladi (asil duzeltmenin tam tersi). Bu
# yuzden artik LLM'e hic gosterilmiyorlar; `_ayikla_korunan_bloklar` onlari
# metinden cikarip merge SONRASI kod tarafindan aynen ekliyor.
# ---------------------------------------------------------------------------


def test_ayikla_tam_kuyruk_soundaki_dusuk_guven_cumlesiyle_birlikte_cikar():
    """risk_agent'in blogu KENDI ICINDE bir '\\n\\n' tasir (madde listesi ile
    dusuk-guven cumlesi arasinda) — yine de TEK blok olarak, boluenmeden
    cikmali (bu blok metnin KESIN SONUdur, ortasinda baska blok gelmez)."""
    text = (
        "Risk seviyesi: Çok Düşük\n\n"
        "Varlık bazlı gözlemler\n"
        "- IOO (%37,60, Yoğunlaşma): açıklama\n\n"
        "Bu gözlemler sınırlı sayıda kaynağa dayanıyor; kapsamı dar olabilir."
    )

    kalan, bloklar = _ayikla_korunan_bloklar(text)

    assert len(bloklar) == 1
    assert bloklar[0] == (
        "Varlık bazlı gözlemler\n"
        "- IOO (%37,60, Yoğunlaşma): açıklama\n\n"
        "Bu gözlemler sınırlı sayıda kaynağa dayanıyor; kapsamı dar olabilir."
    )
    # Ham ayrıntı (sembol, yüzde) LLM'in göreceği metinde KALMAMALI.
    assert "IOO" not in kalan
    assert "%37,60" not in kalan
    assert "[NOT — kullanıcıya gösterme:" in kalan
    assert "Risk seviyesi: Çok Düşük" in kalan


def test_ayikla_sinirli_kuyruk_kendinden_sonraki_bloga_dokunmaz():
    """portfolio_agent'daki 'Risk profili uyumu' blogu ORTADA olabilir
    (Performans gibi bloklar ardindan gelebilir) — yalnizca kendisi
    cikmali, sonraki blok LLM'in gorecegi metinde AYNEN kalmali."""
    text = (
        "Varlıklar\nIOO ...\n\n"
        "Risk profili uyumu\n"
        "Elinizde, güncel risk profilinize göre artık tavsiye kapsamında "
        "olmayan şu varlıklar var: IOO (Borçlanma Araçları, uygunluk seviyesi 2). "
        "Anket puanınız 1. Bu bir satış zorunluluğu değildir, yalnızca "
        "bilgilendirmedir.\n\n"
        "Performans\nDönem değişimi: +%1,00"
    )

    kalan, bloklar = _ayikla_korunan_bloklar(text)

    assert len(bloklar) == 1
    assert bloklar[0].startswith("Risk profili uyumu")
    assert "uygunluk seviyesi 2" in bloklar[0]
    # Sonraki blok, LLM'in gorecegi metinde kaybolmamali.
    assert "Performans\nDönem değişimi: +%1,00" in kalan
    # Ham ayrıntı (sembol, seviye, puan) LLM'in göreceği metinde KALMAMALI.
    assert "uygunluk seviyesi 2" not in kalan
    assert "Anket puanınız 1" not in kalan
    assert "[NOT — kullanıcıya gösterme:" in kalan


def test_ayikla_baslik_yoksa_metne_dokunmaz():
    text = "Portföy özeti\nToplam değer: 100 TL"

    kalan, bloklar = _ayikla_korunan_bloklar(text)

    assert kalan == text
    assert bloklar == []


async def test_merge_varlik_bazli_gozlemler_LLM_ne_yazarsa_yazsin_kaybolmaz():
    """Asil regresyon (2026-08-31, canli arayuz testi): blok yalnizca
    prompt talimatiyla korunuyordu ve LLM basligi + maddeleri dusurup
    yalnizca kapanis cumlesini biraktı. Artik LLM'e hic gosterilmiyor;
    LLM ne cevap uydurursa uydursun blok yanita AYNEN eklenmeli."""
    import agents.orchestrator as orch

    class _BlogdanHabersizLLM:
        async def stream(self, prompt, system=None):
            # Canlida oldugu gibi: blok icerigine hic deginmeyen kisa bir
            # cevap - LLM'in ne yazdigi ARTIK ONEMLI DEGIL.
            yield "Portföyünüz düşük riskli."

    original = orch.get_llm_client
    orch.get_llm_client = lambda: _BlogdanHabersizLLM()
    try:
        state = {
            "message": "portföyümün risk seviyesi nedir",
            "agent_responses": [
                _Response(
                    True,
                    summary_text=(
                        "Risk seviyesi: Çok Düşük\n\n"
                        "Varlık bazlı gözlemler\n"
                        "- IOO (%37,60, Yoğunlaşma): açıklama\n\n"
                        "Bu gözlemler sınırlı sayıda kaynağa dayanıyor; "
                        "kapsamı dar olabilir."
                    ),
                )
            ],
        }
        result = await merge_responses(state, lambda chunk: None)
    finally:
        orch.get_llm_client = original

    assert "Varlık bazlı gözlemler" in result["final_answer"]
    assert "IOO (%37,60, Yoğunlaşma): açıklama" in result["final_answer"]
    assert "Bu gözlemler sınırlı sayıda kaynağa dayanıyor" in result["final_answer"]
    assert "Portföyünüz düşük riskli." in result["final_answer"]


async def test_merge_risk_profili_uyumu_sinifa_geri_yorumlanamaz():
    """Ikinci regresyon: bu blok hic korunmuyordu, LLM onu SINIF duzeyine
    geri yorumladi ('Borçlanma Araçları sınıfı ... artık tavsiye kapsamında
    değil') — 2026-08-31'de asset-level'e tasinarak duzeltilen hatanin
    aynisi. Artik LLM'e ayrinti hic gosterilmiyor, o yuzden uydurmaya
    zemin de kalmiyor; dogru (sembol + kendi seviyesi) blok AYNEN eklenir."""
    import agents.orchestrator as orch

    class _SinifDuzeyineYorumlayanLLM:
        async def stream(self, prompt, system=None):
            # Tam olarak canlida olculen hatali cevap sekli.
            yield "Borçlanma Araçları sınıfı güncel profilinize göre artık tavsiye kapsamında değil."

    original = orch.get_llm_client
    orch.get_llm_client = lambda: _SinifDuzeyineYorumlayanLLM()
    try:
        state = {
            "message": "portföyümdeki varlıklar risk profilime uyuyor mu",
            "agent_responses": [
                _Response(
                    True,
                    summary_text=(
                        "Risk profili uyumu\n"
                        "Elinizde, güncel risk profilinize göre artık tavsiye "
                        "kapsamında olmayan şu varlıklar var: IOO (Borçlanma "
                        "Araçları, uygunluk seviyesi 2). Anket puanınız 1. Bu "
                        "bir satış zorunluluğu değildir, yalnızca "
                        "bilgilendirmedir."
                    ),
                )
            ],
        }
        result = await merge_responses(state, lambda chunk: None)
    finally:
        orch.get_llm_client = original

    # Dogru, sembol-bazli blok AYNEN yanitta olmali.
    assert "IOO (Borçlanma Araçları, uygunluk seviyesi 2)" in result["final_answer"]
    assert "Anket puanınız 1" in result["final_answer"]


async def test_merge_korunan_blok_LLM_promptunda_ham_ayrinti_tasimaz():
    """LLM'e giden metinde artik ham sembol/seviye/yuzde OLMAMALI — yanlis
    yorumlayamasin diye. Yalnizca kisa bir NOT kalir."""
    llm = await _merge_ile_calistir(
        {
            "message": "portföyümdeki varlıklar risk profilime uyuyor mu",
            "agent_responses": [
                _Response(
                    True,
                    summary_text=(
                        "Risk profili uyumu\n"
                        "Elinizde ... IOO (Borçlanma Araçları, uygunluk "
                        "seviyesi 2). Anket puanınız 1. Bu bir satış "
                        "zorunluluğu değildir, yalnızca bilgilendirmedir."
                    ),
                )
            ],
        }
    )

    assert "uygunluk seviyesi 2" not in llm.prompt
    assert "Anket puanınız 1" not in llm.prompt
    assert "[NOT — kullanıcıya gösterme: 'Risk profili uyumu'" in llm.prompt


async def test_merge_llm_sessiz_kalirsa_korunan_blok_iki_kez_gorunmez():
    """LLM hic parca uretmezse ham metin (`successful_raw`) kullanilir; blok
    zaten dogal yerinde durdugundan AYRICA eklenip TEKRAR ETMEMELI, notun
    kendisi de sizmamali."""
    import agents.orchestrator as orch

    class _SessizLLM:
        async def stream(self, prompt, system=None):
            return
            yield  # pragma: no cover - üretici yapmak için

    original = orch.get_llm_client
    orch.get_llm_client = lambda: _SessizLLM()
    try:
        state = {
            "agent_responses": [
                _Response(
                    True,
                    summary_text=(
                        "Risk seviyesi: Çok Düşük\n\nVarlık bazlı gözlemler\n"
                        "- IOO (%37,60, Yoğunlaşma): açıklama"
                    ),
                )
            ],
        }
        result = await merge_responses(state, lambda chunk: None)
    finally:
        orch.get_llm_client = original

    assert result["final_answer"].count("Varlık bazlı gözlemler") == 1
    assert "[NOT — kullanıcıya gösterme:" not in result["final_answer"]


# ---------------------------------------------------------------------------
# Kaynak takip sorusu — geçmişten cevaplanır
# ---------------------------------------------------------------------------

ONCEKI_YANIT = """THYAO'da son gelişmeler, 2026 ilk yarı sonuçlarının açıklanmasıdır.

Kaynaklar:
- Türk Hava Yolları (THYAO) 2026 2. Çeyrek Finansal Sonuçları (AeroNews24, 05.08.2026)
- Türk Hava Yolları Şirket Profili (THY Yatırımcı İlişkileri / KAP, 20.08.2026)

Güncel KAP Bildirimleri:
- Finansal Rapor (6 Aylık) — 05.08.2026 (https://www.kap.org.tr/tr/Bildirim/1643238)"""

GECMIS = [
    {"role": "user", "content": "THYAO hakkında son gelişmeler neler?"},
    {"role": "assistant", "content": ONCEKI_YANIT},
]


def test_kaynak_sorusu_ONCEKI_YANITTAN_cevaplanir():
    """Ölçüldü (1 Eylül 2026, [32] ve [34]): "Kaynak olarak neye
    dayanıyorsun?" Piyasa Ajanı'na düşüp bu cümlenin KENDİSİ belgelerde
    aranıyor ve "doğrulanmış bilgi bulunamadı" dönüyordu — oysa bir önceki
    yanıt iki kaynağı ve bir KAP bağlantısını listelemişti.

    CLAUDE.md §4 kaynak izlenebilirliğini zorunlu tutuyor; yanıt bunu
    veriyordu ama kullanıcı SONRADAN sorduğunda kayboluyordu.
    """
    yanit = _kaynak_takip_yaniti("Kaynak olarak neye dayanıyorsun?", GECMIS)

    assert yanit is not None
    assert "AeroNews24" in yanit
    assert "kap.org.tr" in yanit
    # Bloklar AYNEN taşınır, yeniden yazılmaz.
    assert "Kaynaklar:" in yanit and "Güncel KAP Bildirimleri:" in yanit


def test_kaynak_sorusu_ILK_MESAJDA_normal_akista_kalir():
    """Geçmiş yoksa "kaynağın ne" sorusu sistemin genel çalışmasını
    soruyordur; önceki yanıt diye bir şey yok."""
    assert _kaynak_takip_yaniti("Kaynak olarak neye dayanıyorsun?", []) is None


def test_kaynak_sorusunda_YENI_KONU_gecerse_devralinmaz():
    """ "Tüpraş kaynakları neler?" bir önceki cevap THYAO hakkındaysa, o
    cevabın kaynaklarını göstermek yanlış olurdu — kullanıcı yeni bir konu
    soruyor."""
    assert _kaynak_takip_yaniti("Tüpraş kaynakları neler?", GECMIS) is None


def test_kaynaksiz_yanitta_DURUSTCE_soylenir():
    """Fiyat/portföy cevapları arşiv belgesine dayanmıyor; "kaynak yok"
    demek yerine nereden geldiği söylenir (AK 5.5)."""
    gecmis = [{"role": "assistant", "content": "Amerikan Doları 48,26 TL (31.08.2026, TCMB)."}]

    yanit = _kaynak_takip_yaniti("Neye dayanıyorsun?", gecmis)

    assert yanit is not None
    assert "kaynak listesi taşımıyordu" in yanit


def test_kaynak_kalibi_yoksa_bu_yola_girilmez():
    assert _kaynak_takip_yaniti("Portföyüm ne durumda?", GECMIS) is None


def test_SOURCE_RECALL_erken_cikis_listesinde():
    """Yanıt geçmişten üretildi; ajana gitmesine gerek yok."""
    from agents.orchestrator import _route_after_intent

    assert _route_after_intent({"intent": "SOURCE_RECALL"}) == ["handle_out_of_scope"]
