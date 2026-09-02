"""Analist Ajanı sözleşme testleri.

NEDEN VAR. Ajan `test` dalına, `execute`'un ilk satırında `AttributeError`
atarak girdi: `AgentRequest`'te `message` alanı yok (adı `query`), sınıfta
`agent_name` tanımlı değildi ve `BaseAgent._get_llm` diye bir metot yok. Üçü
de ancak ajan GERÇEKTEN çalıştırıldığında görünen kusurlar; hiçbir test
ajanı çalıştırmıyordu.

Buradaki testler ne LLM'e ne MCP'ye gider — ikisi de sahte. Sınanan şey
ajanın iş zekâsı değil, **sözleşmeye uyup uymadığı**: doğru alan adları,
zorunlu yanıt alanları, doğru tool adları/argümanları ve dış servis
düştüğünde zarif düşüş.
"""

import pytest

from agents.analyst_agent import AnalystAgent
from agents.base import AgentRequest, AgentResponse

SORU = "Aselsan bilançosu ne anlama geliyor, hisse ucuz mu?"


class SahteLLM:
    """Prompt'u kaydeder, sabit metin döndürür."""

    def __init__(self) -> None:
        self.system: str | None = None
        self.prompt: str | None = None

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.prompt = prompt
        self.system = system
        return "Analitik yorum."


class SahteAjan(AnalystAgent):
    """Tool çağrılarını kaydeder, hepsine başarılı zarf döndürür."""

    def __init__(self) -> None:
        super().__init__(mcp_server_url="http://kullanilmiyor")
        self.cagrilar: list[tuple[str, dict]] = []

    async def call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        self.cagrilar.append((tool_name, arguments))
        return {
            "success": True,
            "data": {"records": {"ASELS": {"pe": 12.4}}, "risk_profile": "aggressive"},
        }


class MCPKapali(SahteAjan):
    async def call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        raise RuntimeError("MCP sunucusuna ulaşılamıyor")


@pytest.fixture()
def sahte_llm(monkeypatch):
    llm = SahteLLM()
    monkeypatch.setattr("agents.analyst_agent.get_llm_client", lambda: llm)
    return llm


def _istek(query: str = SORU) -> AgentRequest:
    return AgentRequest(user_id="11111111-1111-1111-1111-111111111111", session_id="s", query=query)


async def test_ajan_CALISIR_ve_gecerli_yanit_dondurur(sahte_llm):
    """Kaçırılan hata tam buydu: ajan hiç çalışmıyordu.

    `AgentResponse.agent_name` ve `summary_text` zorunlu alanlar; eksik
    bırakıldığında pydantic her yanıt üretiminde ValidationError atıyordu.
    """
    yanit = await SahteAjan().execute(_istek())

    assert isinstance(yanit, AgentResponse)
    assert yanit.success is True
    assert yanit.agent_name == "analyst"
    assert "Analitik yorum." in yanit.summary_text


async def test_soru_metni_QUERY_alanindan_okunur(sahte_llm):
    """`request.message` diye bir alan yok. Sorunun prompt'a gerçekten
    geçtiğini doğrulamak, alan adının bir daha kaymasını engelliyor."""
    await SahteAjan().execute(_istek())

    assert SORU in (sahte_llm.prompt or "")


async def test_dogru_TOOL_ADLARIYLA_cagirir(sahte_llm):
    """Tool adları MCP'de kayıtlı adlarla birebir olmalı; yanlış ad sessizce
    boş veri üretir, ajan da 'veri yok' der — hata gibi görünmez."""
    ajan = SahteAjan()
    await ajan.execute(_istek())
    adlar = {ad for ad, _ in ajan.cagrilar}

    assert {
        "get_user_risk_survey",
        "get_target_prices",
        "get_current_prices",
        "get_fundamentals",
        "search_market_news",
        "get_asset_price_history",
    } <= adlar


async def test_endeks_kiyaslamasi_EVRENDEKI_sembolu_kullanir(sahte_llm):
    """`XU100.IS` sağlayıcı sembolüdür; `price_history` onu tanımaz.

    Yanlış sembolle endeks verisi hiç gelmiyor ama model yine de 'endekse
    göre' cümlesi kurabiliyordu — sessiz ve yanıltıcı bir kayıp.
    """
    ajan = SahteAjan()
    await ajan.execute(_istek())
    endeks = [args for ad, args in ajan.cagrilar if ad == "get_asset_price_history"]

    assert endeks, "endeks kıyaslaması hiç çağrılmadı"
    assert endeks[0]["symbols"] == ["XU100"]


async def test_MCP_DUSERSE_yanit_yine_uretilir(sahte_llm):
    """Zarif düşüş (CLAUDE.md §4): risk profili alınamazsa kişiselleştirme
    kaybolur, cevap kaybolmaz. Önceden bu çağrı `execute`'un ilk satırındaydı
    ve korumasızdı, dolayısıyla ajanın kendi 'Bilinmiyor' yedeğine hiçbir
    zaman düşülemiyordu."""
    yanit = await MCPKapali().execute(_istek())

    assert yanit.success is True
    assert "Analitik yorum." in yanit.summary_text
    assert "Bilinmiyor" in (sahte_llm.system or "")


async def test_sirket_tespit_edilemezse_DURUSTCE_soyler(sahte_llm):
    """Şirketsiz soruda uydurma veri üretilmemeli (AK 5.5)."""
    await SahteAjan().execute(_istek("bu haber piyasayı nasıl fiyatlar?"))

    assert "tespit edilemedi" in (sahte_llm.system or "")


async def test_en_fazla_UC_SIRKET_islenir(sahte_llm):
    """Hız/token sınırı için ilk 3 şirketle sınırlı. Sınır değişirse bu test
    kırılır ve kullanıcıya 'ikisini yuttum' denip denmediği yeniden
    düşünülür."""
    ajan = SahteAjan()
    await ajan.execute(_istek("Akbank, Garanti, İş Bankası, Yapı Kredi ve Vakıfbank'ı karşılaştır"))
    hedef_cagrilari = [args for ad, args in ajan.cagrilar if ad == "get_target_prices"]

    assert len(hedef_cagrilari) <= 3


async def test_LLM_DUSERSE_hata_yaniti_gecerlidir(monkeypatch):
    """Hata dalı da `AgentResponse` üretiyor; orada da zorunlu alanlar vardı
    ve eksikti — except bloğunun kendisi patlıyordu."""

    class PatlakLLM:
        async def generate(self, prompt: str, *, system: str | None = None) -> str:
            raise RuntimeError("LLM yok")

    monkeypatch.setattr("agents.analyst_agent.get_llm_client", lambda: PatlakLLM())
    yanit = await SahteAjan().execute(_istek())

    assert isinstance(yanit, AgentResponse)
    assert yanit.success is False
    assert yanit.agent_name == "analyst"
    assert yanit.error


async def test_SIRKETIN_KENDI_fiyat_serisini_de_ceker(sahte_llm):
    """Endeksin serisi çekiliyordu ama şirketinki hiç istenmiyordu.

    Ölçüldü (1 Eylül 2026): beş analiz yanıtının beşi de aynı cümleyle
    bitiyordu — "hisseye ait üç aylık fiyat serisi bulunmadığı için endekse
    göre karşılaştırma yapılamıyor". Prompt kuralı 7 bağıl performans yorumu
    istiyor; girdisi eksikti.
    """
    ajan = SahteAjan()
    await ajan.execute(_istek("Aselsan endekse göre nasıl performans gösterdi?"))
    seri_cagrilari = [args for ad, args in ajan.cagrilar if ad == "get_asset_price_history"]
    istenen = {tuple(a["symbols"]) for a in seri_cagrilari}

    assert ("ASELS",) in istenen, f"şirketin serisi istenmedi: {istenen}"
    assert ("XU100",) in istenen, f"endeksin serisi istenmedi: {istenen}"
    # İki seri AYNI pencerede olmalı, yoksa farklı dönemler kıyaslanır.
    assert {a["window"] for a in seri_cagrilari} == {"3m"}
