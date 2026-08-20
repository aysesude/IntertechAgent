"""Orchestrator: kapsam filtresi, niyet yönlendirmesi ve yanıt birleştirme.

Bu dosyadaki testlerin çoğu üretimde gözlenmiş üç somut arızayı sabitler:
1. Kapsam filtresi alt dizi araması yaptığı için "portföy analizi" gibi meşru
   sorular "işlem talebi" sayılıp reddediliyordu.
2. "Riskim ne durumda" sorusunun gidebileceği bir ajan yoktu.
3. Birleştirme LLM'i istisna atmadan boş yanıt döndürdüğünde kullanıcıya ne
   metin ne hata gidiyordu — arayüzde boş balon kalıyordu.

DB gerektirmez; LLM istemcisi sahte (fake) nesnelerle değiştirilir.
"""

from collections.abc import AsyncIterator

import pytest

from agents import orchestrator
from agents.base import AgentResponse


class _FakeLLM:
    """generate() sabit metin, stream() sabit parça listesi döner."""

    def __init__(self, reply: str = "", chunks: list[str] | None = None) -> None:
        self._reply = reply
        self._chunks = chunks if chunks is not None else [reply]

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return self._reply

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk


class _BrokenLLM:
    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        raise RuntimeError("LLM erisilemiyor")

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        raise RuntimeError("LLM erisilemiyor")
        yield ""  # pragma: no cover - async generator seklini korumak icin


def _use_llm(monkeypatch, client) -> None:
    monkeypatch.setattr(orchestrator, "get_llm_client", lambda: client)


def _state(message: str, responses: list[AgentResponse] | None = None) -> dict:
    return {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "session_id": "22222222-2222-2222-2222-222222222222",
        "message": message,
        "history": [],
        "intent": "",
        "targets": [],
        "agent_responses": responses or [],
        "final_answer": "",
    }


class _Writer:
    """StreamWriter yerine geçer: akıtılan deltaları biriktirir."""

    def __init__(self) -> None:
        self.deltas: list[str] = []

    def __call__(self, chunk: dict) -> None:
        self.deltas.append(chunk["delta"])

    @property
    def text(self) -> str:
        return "".join(self.deltas)


# --------------------------------------------------------------------------
# Kapsam filtresi
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "portföy analizi",
        "portföyümü analiz et",
        "altın ne durumda",
        "havacılık hisseleri nasıl",
        "kâr zarar durumum ne",
        "portföyümde ne kadar altın var",
    ],
)
async def test_kapsam_filtresi_mesru_sorulari_reddetmez(monkeypatch, query):
    """Eski filtre alt dizi arıyordu: "an-AL-iz", "AL-tın", "HAVA-cılık"
    kelimelerinin içindeki tesadüfi eşleşmeler yüzünden bu soruların hepsi
    "Bu işlemi gerçekleştirmeye yetkim bulunmuyor" cevabı alıyordu."""
    _use_llm(monkeypatch, _FakeLLM(reply="PORTFOLIO"))

    result = await orchestrator.detect_intent(_state(query))

    assert result["intent"] != "out_of_scope", f"mesru soru reddedildi: {query}"
    assert result["targets"] != ["handle_out_of_scope"]


@pytest.mark.parametrize(
    "query",
    [
        "1000 TL transfer et",
        "hisse al",
        "altınlarımı sat",
        "arkadaşıma para gönder",
        "10 lot satın al",
    ],
)
async def test_kapsam_filtresi_islem_taleplerini_reddeder(monkeypatch, query):
    _use_llm(monkeypatch, _FakeLLM(reply="PORTFOLIO"))

    result = await orchestrator.detect_intent(_state(query))

    assert result["intent"] == "out_of_scope"
    assert result["targets"] == ["handle_out_of_scope"]
    assert result["final_answer"]


async def test_kapsam_filtresi_finans_disi_sohbeti_reddeder(monkeypatch):
    _use_llm(monkeypatch, _FakeLLM(reply="PORTFOLIO"))

    result = await orchestrator.detect_intent(_state("bugün hava nasıl"))

    assert result["intent"] == "out_of_scope"


# --------------------------------------------------------------------------
# Niyet yönlendirmesi
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("llm_reply", "expected"),
    [
        ("PORTFOLIO", ["portfolio_agent"]),
        ("MARKET", ["market_agent"]),
        ("RISK", ["risk_agent"]),
        ("PORTFOLIO, MARKET", ["portfolio_agent", "market_agent"]),
        ("RISK, MARKET", ["market_agent", "risk_agent"]),
        ("BOTH", ["portfolio_agent", "market_agent"]),  # eski surumle uyum
        ("Cevap: PORTFOLIO", ["portfolio_agent"]),  # serbest metin yanit
    ],
)
async def test_niyet_tespiti_hedef_ajanlari_secer(monkeypatch, llm_reply, expected):
    _use_llm(monkeypatch, _FakeLLM(reply=llm_reply))

    result = await orchestrator.detect_intent(_state("soru"))

    assert result["targets"] == expected


async def test_risk_sorusu_risk_ajanina_gider(monkeypatch):
    """Risk ajanı grafa bağlanmadan önce "riskim yüksek mi" sorusu zorunlu
    olarak portföy ya da piyasa ajanına düşüyordu; ikisi de cevaplayamıyordu."""
    _use_llm(monkeypatch, _FakeLLM(reply="RISK"))

    result = await orchestrator.detect_intent(_state("riskim yüksek mi"))

    assert result["targets"] == ["risk_agent"]


async def test_niyet_tespiti_llm_hatasinda_portfoye_duser(monkeypatch):
    """Zarif düşüş (CLAUDE.md §4): sınıflandırma LLM'i düşse bile soru
    cevapsız kalmaz."""
    _use_llm(monkeypatch, _BrokenLLM())

    result = await orchestrator.detect_intent(_state("portföyüm ne durumda"))

    assert result["targets"] == ["portfolio_agent"]


# --------------------------------------------------------------------------
# Yanıt birleştirme
# --------------------------------------------------------------------------


def _ok(agent_name: str, text: str) -> AgentResponse:
    return AgentResponse(agent_name=agent_name, success=True, summary_text=text)


def _fail(agent_name: str, error: str) -> AgentResponse:
    return AgentResponse(agent_name=agent_name, success=False, summary_text="", error=error)


async def test_merge_tek_ajanda_llm_cagirmaz(monkeypatch):
    """Tek ajanın metni zaten kullanıcıya hazır; ikinci bir LLM turu bilgi
    eklemeden gecikme ve kırılma noktası ekler."""

    def _bosuna_cagrildi():
        raise AssertionError("merge tek ajan varken LLM cagirmamali")

    monkeypatch.setattr(orchestrator, "get_llm_client", _bosuna_cagrildi)
    writer = _Writer()

    result = await orchestrator.merge_responses(
        _state("portföyüm", [_ok("portfolio_agent", "Portföyünüz 100.000,00 TL değerinde.")]),
        writer,
    )

    assert "100.000,00 TL" in result["final_answer"]
    assert writer.text == result["final_answer"]


async def test_merge_llm_bos_donerse_bos_cevap_birakmaz(monkeypatch):
    """Üretimde gözlenen arıza: birleştirme LLM'i istisna atmadan hiç parça
    üretmediğinde ne token ne hata gidiyordu, arayüzde boş balon kalıyordu."""
    _use_llm(monkeypatch, _FakeLLM(chunks=[]))
    writer = _Writer()

    result = await orchestrator.merge_responses(
        _state(
            "portföyüm ve haberler",
            [
                _ok("portfolio_agent", "Portföyünüz 100.000,00 TL."),
                _ok("market_agent", "BIST 100 yükseldi."),
            ],
        ),
        writer,
    )

    assert writer.deltas, "kullaniciya hicbir sey akitilmadi"
    assert "100.000,00 TL" in result["final_answer"]
    assert "BIST 100" in result["final_answer"]


async def test_merge_llm_hatasinda_ham_metinlere_duser(monkeypatch):
    _use_llm(monkeypatch, _BrokenLLM())
    writer = _Writer()

    result = await orchestrator.merge_responses(
        _state(
            "portföyüm ve haberler",
            [
                _ok("portfolio_agent", "Portföyünüz 100.000,00 TL."),
                _ok("market_agent", "BIST 100 yükseldi."),
            ],
        ),
        writer,
    )

    assert "100.000,00 TL" in result["final_answer"]
    assert writer.text == result["final_answer"]


async def test_merge_hicbir_ajan_basarili_degilse_tool_mesajini_gosterir(monkeypatch):
    """Tool hata mesajları kullanıcıya gösterilmek üzere yazılmıştır
    (mcp_server/tools/_base.py DEFAULT_MESSAGES); genel bir "sistem hatası"
    metniyle değiştirmek bilgi kaybıdır."""

    def _bosuna_cagrildi():
        raise AssertionError("basarili yanit yokken LLM cagirilmamali")

    monkeypatch.setattr(orchestrator, "get_llm_client", _bosuna_cagrildi)
    writer = _Writer()
    mesaj = "Veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı."

    result = await orchestrator.merge_responses(
        _state("aselsan haber", [_fail("market_agent", mesaj)]), writer
    )

    assert mesaj in result["final_answer"]
    assert writer.deltas


async def test_merge_hic_yanit_yoksa_sistem_mesaji_doner(monkeypatch):
    def _bosuna_cagrildi():
        raise AssertionError("yanit yokken LLM cagirilmamali")

    monkeypatch.setattr(orchestrator, "get_llm_client", _bosuna_cagrildi)
    writer = _Writer()

    result = await orchestrator.merge_responses(_state("soru", []), writer)

    assert orchestrator.SYSTEM_UNAVAILABLE_MESSAGE in result["final_answer"]


async def test_merge_her_yolda_sorumluluk_reddi_ekler(monkeypatch):
    """CLAUDE.md §4: her finansal çıktı bu ibareyi taşımalı. LLM'in eklemesine
    güvenilmez."""
    _use_llm(monkeypatch, _FakeLLM(chunks=["Birleştirilmiş yanıt."]))

    senaryolar = [
        [_ok("portfolio_agent", "Tek ajan yanıtı.")],
        [_ok("portfolio_agent", "Bir."), _ok("risk_agent", "İki.")],
        [_fail("market_agent", "Bulunamadı.")],
        [],
    ]

    for responses in senaryolar:
        writer = _Writer()
        result = await orchestrator.merge_responses(_state("soru", responses), writer)
        assert orchestrator.DISCLAIMER in result["final_answer"], responses


async def test_merge_sorumluluk_reddini_ikilemez(monkeypatch):
    """Ajan metni uyarıyı zaten taşıyorsa (risk_service'in INVESTMENT_DISCLAIMER
    metni gibi) ikinci kez eklenmemeli."""

    def _bosuna_cagrildi():
        raise AssertionError("tek ajanda LLM cagirilmamali")

    monkeypatch.setattr(orchestrator, "get_llm_client", _bosuna_cagrildi)
    writer = _Writer()
    metin = f"Riskiniz Orta seviyede. {orchestrator.DISCLAIMER}"

    result = await orchestrator.merge_responses(
        _state("riskim", [_ok("risk_agent", metin)]), writer
    )

    assert result["final_answer"].count(orchestrator.DISCLAIMER) == 1


# --------------------------------------------------------------------------
# Graf
# --------------------------------------------------------------------------


def test_graf_uc_ajani_da_icerir():
    """Risk ajanı grafa bağlı değilse niyet tespiti onu seçse bile
    çalışmaz — bu test o kopukluğu yakalar."""
    nodes = orchestrator._compiled_graph.get_graph().nodes

    assert {"portfolio_agent", "market_agent", "risk_agent", "merge"} <= set(nodes)
