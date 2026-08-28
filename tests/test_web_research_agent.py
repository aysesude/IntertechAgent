"""Web Araştırma Ajanı testleri.

LLM'e gerçekten gidilmez: `get_llm_client` yerine sahte bir istemci konur ve
ajana giden prompt yakalanır. Test edilen şey modelin cevabı değil, ajanın
prompt'a hangi kuralları koyduğu ve boş/hatalı yanıtta ne yaptığı.
"""

import pytest

from agents import web_research_agent as wr
from agents.base import AgentRequest


class SahteLLM:
    """Verilen parçaları akıtan, istenirse patlayan LLM istemcisi."""

    def __init__(self, parcalar=("Lot, ", "bir pay ", "birimidir."), patlat=False):
        self.parcalar = parcalar
        self.patlat = patlat
        self.son_prompt = None

    async def stream(self, prompt, *, system=None):
        self.son_prompt = prompt
        if self.patlat:
            raise RuntimeError("ag gecidi kapali")
        for parca in self.parcalar:
            yield parca


def _istek(query: str) -> AgentRequest:
    return AgentRequest(user_id="u1", session_id="s1", query=query)


def _ajan() -> wr.WebResearchAgent:
    # MCP adresi kullanılmıyor (ajan tool çağırmıyor) ama BaseAgent istiyor.
    return wr.WebResearchAgent(mcp_server_url="http://kullanilmiyor")


# ---------------------------------------------------------------------------
# Kısıtlı konu tespiti — kurallar scope.yaml'dan okunur, kodda liste yok
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "temettü vergisi nasıl hesaplanır",
        "stopajdan muaf mıyım",
        "beyanname ne zaman verilir",
    ],
)
def test_vergi_sorulari_kisitli_isaretlenir(query):
    assert "vergi" in wr._restricted_topics(query)


@pytest.mark.parametrize("query", ["lot ne demek", "borsa saat kaçta kapanır"])
def test_duz_kavram_sorusu_kisit_tasimaz(query):
    assert wr._restricted_topics(query) == []


def test_kisit_blogu_scope_yaml_kurallarini_tasir():
    blok = wr._restriction_block(["vergi"])
    assert "SAYI VERME" in blok
    # Yönlendirme metni scope.yaml'dan gelir, ajanda yeniden yazılmaz.
    assert "mali müşavire" in blok
    assert "durumunuza göre değişir" in blok


def test_kisit_yoksa_blok_bostur():
    assert wr._restriction_block([]) == ""


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


async def test_execute_llm_metnini_dondurur(monkeypatch):
    sahte = SahteLLM()
    monkeypatch.setattr(wr, "get_llm_client", lambda: sahte)

    cevap = await _ajan().execute(_istek("lot ne demek"))

    assert cevap.success is True
    assert cevap.summary_text == "Lot, bir pay birimidir."
    assert cevap.data == {"restricted_topics": []}
    # Soru prompt'a girmiş olmalı.
    assert "lot ne demek" in sahte.son_prompt


async def test_execute_vergi_sorusunda_kisit_blogunu_prompta_koyar(monkeypatch):
    sahte = SahteLLM()
    monkeypatch.setattr(wr, "get_llm_client", lambda: sahte)

    cevap = await _ajan().execute(_istek("temettü vergisi nedir"))

    assert cevap.data == {"restricted_topics": ["vergi"]}
    assert "KISITLI KONU" in sahte.son_prompt
    assert "mali müşavire" in sahte.son_prompt


async def test_execute_token_geri_cagrisini_besler(monkeypatch):
    monkeypatch.setattr(wr, "get_llm_client", lambda: SahteLLM(("a", "b", "c")))
    toplanan = []

    await _ajan().execute(_istek("lot ne demek"), on_token=toplanan.append)

    assert toplanan == ["a", "b", "c"]


async def test_execute_bos_yanitta_basarili_donmez(monkeypatch):
    """Boş metinle success=True dönmek yasak: merge onu başarı sayıp
    kullanıcıya bomboş bir baloncuk gösteriyor ve hiçbir yerde hata
    görünmüyor (portfolio_agent'taki aynı koruma)."""
    monkeypatch.setattr(wr, "get_llm_client", lambda: SahteLLM(("", "   ")))

    cevap = await _ajan().execute(_istek("lot ne demek"))

    assert cevap.success is False
    assert cevap.error


async def test_execute_llm_patlarsa_ajan_cokmez(monkeypatch):
    monkeypatch.setattr(wr, "get_llm_client", lambda: SahteLLM(patlat=True))

    cevap = await _ajan().execute(_istek("lot ne demek"))

    assert cevap.success is False
    # İç hata gizliliği: istisna metni kullanıcıya gitmez.
    assert "ag gecidi" not in (cevap.error or "")


# ---------------------------------------------------------------------------
# Prompt sözleşmesi — ajanın uymak zorunda olduğu sınırlar
# ---------------------------------------------------------------------------


def test_promptta_gecerli_soru_bicimleri_sayili():
    """Kapsam "x nedir" ile sınırlı değil.

    Kullanıcı aynı konuyu "nasıl hesaplanır" ya da "ne sıklıkla olur" diye de
    soruyor; ikisi de kavram sorusudur ve prompt bunları saymalı, yoksa model
    yalnızca tanım sorularını kendi işi sayar.
    """
    metin = " ".join(wr._PROMPT_TEMPLATE.split())
    assert "SANA GELEN SORU BİÇİMLERİ" in metin
    for bicim in ["nasıl hesaplanır", "ne sıklıkla", "arasındaki fark", "ne zaman"]:
        assert bicim in metin, bicim


def test_promptta_degiskenlik_uyarisi_var():
    """Sıklık soruları şirkete göre değişir.

    Örnek: temettünün ne sıklıkla verildiği genel kurul kararına bağlıdır; tek
    bir sayıyı evrensel kural gibi sunmak yanlış olur.
    """
    metin = " ".join(wr._PROMPT_TEMPLATE.split())
    assert "kesinlik iddia etme" in metin
    assert "şirketten şirkete değişir" in metin


def test_promptta_hesaplama_sorusu_ev_kurallarina_baglanir():
    """Hesaplama sorusu bu uygulamanın tanımına bağlanmalı.

    Örnek: kâr oranının nasıl hesaplandığı sorulduğunda ders kitabı formülü
    değil, ekrandaki rakamı üreten tanım anlatılmalı.
    """
    metin = " ".join(wr._PROMPT_TEMPLATE.split())
    assert "önce EV KURALLARI'na bak" in metin


def test_promptta_ev_kurallari_yazili():
    """Bu uygulamanın kendi hesap tanımları prompt'ta olmalı.

    "Portföy kârı nasıl hesaplanır" sorusuna ders kitabı cevabı vermek,
    açıklamayla ekrandaki rakamın birbirini yalanlaması demek: ikisi de kendi
    içinde tutarlı ama kullanıcı hangisine güveneceğini bilemez.
    """
    # Satır sarmalarına takılmamak için boşluklar tek boşluğa indirgenir;
    # prompt yeniden biçimlendiğinde test kırılmamalı.
    metin = " ".join(wr._PROMPT_TEMPLATE.split())
    assert "EV KURALLARI" in metin
    # Kâr tabanı: holdings maliyeti değil, dışarıdan konan net sermaye.
    assert "net sermaye" in metin
    # Dönem getirisi TWR; para yatırmak getiri sayılmaz.
    assert "zaman ağırlıklı getiri (TWR)" in metin
    # Kıyaslamada t0 miktarları sabit.
    assert "SABİT tutulur" in metin
    # Ağırlık paydası nakit dahil.
    assert "NAKİT DAHİL" in metin


def test_promptta_temel_sinirlar_yazili():
    metin = " ".join(wr._PROMPT_TEMPLATE.split())
    # Portföye atıf yasağı: ajan o veriyi görmüyor.
    assert "portföyüne ASLA atıf yapma" in metin
    # Güncel piyasa değeri yasağı: piyasa ajanının işi.
    assert "Güncel fiyat, kur, faiz oranı, endeks değeri VERME" in metin
    # Değişebilen olgularda kaynak zorunluluğu (kullanıcı kararı).
    assert "resmî kaynağı işaret et" in metin
