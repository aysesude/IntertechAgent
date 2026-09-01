"""Özet Ajanı — "kendi sayısı olmayan ajan" sözleşmesinin testleri.

Bu ajanın tek riskli tarafı LLM'in sayı uydurması: kartlar sohbetteki
ajanlarla AYNI portföy hakkında konuşuyor ve farklı sayı söylerlerse 1 Eylül
turunun en pahalı bulgusu (K3 — aynı soruya iki farklı cevap) ürün düzeyinde
geri gelir. `_sayilari_dogrula` bunu prompt'a güvenmeden engelliyor;
testlerin ağırlığı orada.

Ne LLM'e ne MCP'ye gidiliyor — ikisi de sahte.
"""

import json

import pytest

from agents.summary_agent import (
    KART_SIRASI,
    SummaryAgent,
    _sayilari_dogrula,
)

GIRDI = (
    "Toplam değer: 1.583.703,56 TL\n"
    "Toplam kâr/zarar: 333.703,56 TL (+%26,70)\n"
    "En büyük pozisyonun ağırlığı: %22,00"
)


# ---------------------------------------------------------------------------
# Sayı doğrulaması — ajanın sözleşmesi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metin",
    [
        "Portföyünüz 1.583.703,56 TL ve +%26,70 kârda.",
        # Biçim farkı uydurma DEĞİLDİR: binlik ayracı ve sondaki sıfır.
        "Portföyünüz 1583703,56 TL değerinde.",
        "Portföyün %26,7 kârı var.",
        # Ölçüm olmayan küçük tam sayılar muaf: "üç varlık", "ilk 3".
        "Üç varlık portföyün büyük kısmını oluşturuyor, ilk 3 pozisyon ağır basıyor.",
    ],
)
def test_gecerli_metinler_dogrulamadan_GECER(metin):
    assert _sayilari_dogrula(metin, GIRDI)


@pytest.mark.parametrize(
    "metin",
    [
        # Veride olmayan bir yüzde — en tehlikeli uydurma biçimi.
        "Portföyünüz 1.583.703,56 TL, aylık +%4,10 kazandı.",
        # KÜÇÜK ama ÖLÇÜM olan sayı da muaf değil. İlk sürümde eşik ondalık
        # ayrımı yapmıyordu ve "%4,10" doğrulamadan geçiyordu.
        "En büyük pozisyon %8 ağırlıkta.",
        "Portföyde 250.000 TL nakit var.",
    ],
)
def test_uydurma_sayilar_dogrulamadan_GECMEZ(metin):
    assert not _sayilari_dogrula(metin, GIRDI)


# ---------------------------------------------------------------------------
# Kart üretimi
# ---------------------------------------------------------------------------

TOOL_YANITLARI = {
    "get_portfolio_summary": {
        "as_of": "2026-08-31",
        "total_value": 1583703.56,
        "net_invested": 1250000.0,
        "cash_try": 175866.14,
        "total_gain_loss": {"amount": 333703.56, "percent": 26.70},
    },
    "get_portfolio_performance": {
        "as_of": "2026-08-31",
        "series_start": "2026-08-01",
        "summary": {"change_percent": 5.43, "changes": {"daily": 0.42, "weekly": 1.15}},
    },
    "get_holdings": {
        "holdings": [
            {
                "symbol": "ASELS",
                "asset_class": "stock",
                "weight_percent": 22.00,
                "unrealized_pnl_percent": 54.84,
            }
        ],
        "cash_weight_percent": 11.10,
        "best_performer": {"symbol": "ASELS", "unrealized_pnl_percent": 54.84},
        "excluded_symbols": [],
    },
    "get_risk_assessment": {
        "risk_level": "medium_low",
        "risk_profile": "aggressive",
        "is_within_profile": True,
        "metrics": {
            "annualized_volatility_percent": 14.13,
            "value_at_risk_try": 48000.0,
            "max_asset_symbol": "ASELS",
            "max_asset_weight_percent": 22.00,
        },
        "mismatched_holdings": [],
    },
    "get_portfolio_news": {
        "assets": [
            {
                "symbol": "ASELS",
                "documents": [
                    {
                        "baslik": "ASELSAN 2026 2. Çeyrek Finansal Sonuçları",
                        "kaynak": "infoyatirim",
                        "tarih": "2026-08-05",
                    }
                ],
            }
        ],
        "covered_weight_percent": 22.0,
        "confidence": "normal",
    },
}

# Doğrulamadan geçen, verideki sayıları kullanan bir LLM çıktısı.
GECERLI_LLM = json.dumps(
    {
        "genel": "Portföyünüz 1.583.703,56 TL değerinde ve +%26,70 kârda.",
        "portfoy": "En büyük pozisyonunuz ASELS, ağırlığı %22,00.",
        "piyasa": "ASELSAN'ın çeyrek sonuçları yayımlandı.",
        "risk": "Yıllık volatiliteniz %14,13.",
    },
    ensure_ascii=False,
)


class SahteAjan(SummaryAgent):
    def __init__(self, yanitlar=None, dusen=()):
        super().__init__(mcp_server_url="http://kullanilmiyor")
        self._yanitlar = yanitlar if yanitlar is not None else TOOL_YANITLARI
        self._dusen = set(dusen)
        self.cagrilar: list[str] = []

    async def call_mcp_tool(self, tool_name: str, arguments: dict) -> dict:
        self.cagrilar.append(tool_name)
        if tool_name in self._dusen:
            raise RuntimeError(f"{tool_name} ulaşılamıyor")
        veri = self._yanitlar.get(tool_name)
        if veri is None:
            return {"success": False, "error": {"message": "yok"}}
        return {"success": True, "data": veri}


class SahteLLM:
    def __init__(self, cikti: str):
        self.cikti = cikti
        self.system: str | None = None

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.system = system
        return self.cikti


@pytest.fixture()
def llm(monkeypatch):
    def _kur(cikti: str) -> SahteLLM:
        sahte = SahteLLM(cikti)
        monkeypatch.setattr("agents.summary_agent.get_llm_client", lambda: sahte)
        return sahte

    return _kur


async def test_dort_kart_SIRASIYLA_uretilir(llm):
    llm(GECERLI_LLM)
    kartlar = await SahteAjan().kartlari_uret("u")

    assert [k["id"] for k in kartlar] == list(KART_SIRASI)
    assert all(not k["degraded"] for k in kartlar)
    assert "1.583.703,56" in kartlar[0]["body"]


async def test_AYNI_TOOLLAR_cagrilir(llm):
    """Ajanın "kendi sayısı yok" vaadi, diğer ajanlarla AYNI kaynağı
    kullanmasına dayanıyor."""
    llm(GECERLI_LLM)
    ajan = SahteAjan()
    await ajan.kartlari_uret("u")

    assert set(ajan.cagrilar) == {
        "get_portfolio_summary",
        "get_portfolio_performance",
        "get_holdings",
        "get_risk_assessment",
        "get_portfolio_news",
    }


async def test_UYDURMA_SAYILI_kart_degraded_duser(llm):
    """Sözleşmenin can alıcı testi: LLM veride olmayan bir yüzde yazarsa o
    kart kullanıcıya GİTMEZ, deterministik blok gösterilir."""
    llm(
        json.dumps(
            {
                "genel": "Portföyünüz 1.583.703,56 TL ve aylık +%4,10 kazandı.",
                "portfoy": "En büyük pozisyonunuz ASELS, ağırlığı %22,00.",
                "piyasa": "ASELSAN'ın çeyrek sonuçları yayımlandı.",
                "risk": "Yıllık volatiliteniz %14,13.",
            },
            ensure_ascii=False,
        )
    )
    kartlar = {k["id"]: k for k in await SahteAjan().kartlari_uret("u")}

    assert kartlar["genel"]["degraded"] is True
    assert "%4,10" not in kartlar["genel"]["body"]
    assert "Toplam değer" in kartlar["genel"]["body"]
    # Diğer kartlar CEZALANDIRILMAZ — doğrulama kart bazında.
    assert kartlar["portfoy"]["degraded"] is False


async def test_BIR_TOOL_duserse_diger_kartlar_uretilir(llm):
    llm(GECERLI_LLM)
    kartlar = {
        k["id"]: k for k in await SahteAjan(dusen={"get_risk_assessment"}).kartlari_uret("u")
    }

    assert kartlar["risk"]["degraded"] is True
    assert kartlar["genel"]["degraded"] is False


async def test_LLM_DUSERSE_dort_kart_da_deterministik_doner(monkeypatch):
    class PatlakLLM:
        async def generate(self, prompt, *, system=None):
            raise RuntimeError("LLM yok")

    monkeypatch.setattr("agents.summary_agent.get_llm_client", lambda: PatlakLLM())
    kartlar = await SahteAjan().kartlari_uret("u")

    assert len(kartlar) == 4
    assert all(k["degraded"] for k in kartlar)
    # Boş kart YOK: kullanıcı hiçbir koşulda boş panel görmemeli.
    assert all(k["body"].strip() for k in kartlar)


async def test_HIC_VERI_YOKSA_kartlar_durustce_bos_oldugunu_soyler(llm):
    llm(GECERLI_LLM)
    kartlar = await SahteAjan(yanitlar={}).kartlari_uret("u")

    assert len(kartlar) == 4
    assert all(k["degraded"] for k in kartlar)
    assert all("yeterli veri alınamadı" in k["body"] for k in kartlar)


async def test_prompt_deterministik_blogu_TASIR(llm):
    """LLM'in eline yalnızca ölçülmüş satırlar geçmeli; doğrulama da bu
    bloğa karşı yapılıyor."""
    sahte = llm(GECERLI_LLM)
    await SahteAjan().kartlari_uret("u")

    assert "1.583.703,56" in (sahte.system or "")
    assert "[genel]" in (sahte.system or "")
    assert "[risk]" in (sahte.system or "")
