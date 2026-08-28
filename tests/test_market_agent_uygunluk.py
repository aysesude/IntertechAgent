"""Piyasa Ajanı'nın profil-uygunluk bilgilendirmesi testleri (bkz.
agents/market_agent.py modül docstring'i "2026-08-28 eki").

NEDEN VAR. Bu "risk analizi" DEĞİLDİR (o `agents/risk_agent.py`'nin işi) —
anket dolu olduğu HER şirket sorusunda çalışır, yalnızca kullanıcının o an
ELİNDE olan bir varlıkla sınırlı değil (kullanıcı kararı, "her şirket
sorusunda daha mantıklı" — bkz. `advice_eligibility` yorumu, analist onaylı,
agents/risk_agent.py'deki Yol B ile aynı yorum). `agents/portfolio_agent.py`
"sahipse uyumsuz" bildirimiyle KARIŞTIRILMAMALI: buradaki kontrol VARLIK
düzeyinde (`is_asset_advice_allowed`), sahiplikten bağımsız.

Saf fonksiyon testleri gerçek bir MCP çağrısı YAPMAZ; `_fetch_risk_survey_
score` ayrı, sahte-sunucu tabanlı testlerde ele alınır (bkz. tests/
test_portfolio_agent_tools.py'deki aynı desen)."""

from fastmcp import FastMCP

from agents.market_agent import (
    MarketAgent,
    _sirket_varlik_sinifi_uygunluk_disi_mi,
    _uygunluk_blogu,
)

# ---------------------------------------------------------------------------
# _sirket_varlik_sinifi_uygunluk_disi_mi
# ---------------------------------------------------------------------------


def test_bilinen_ve_izinli_varlikta_none_doner():
    """ASELS (STOCK, seviye 5), puan=7 (AGGRESSIVE) ile izinlidir (5<=7)."""
    assert _sirket_varlik_sinifi_uygunluk_disi_mi("ASELS", 7) is None


def test_bilinen_ve_izinsiz_varlikta_sinif_adi_doner():
    """ASELS (STOCK, seviye 5), puan=3 (BALANCED) ile izinli DEĞİLDİR (5>3)."""
    assert _sirket_varlik_sinifi_uygunluk_disi_mi("ASELS", 3) == "Hisse Senedi"


def test_anket_bossa_kontrol_atlanir():
    """`risk_survey_score=None` (anket hiç doldurulmamış) — uydurma yok,
    kontrol tamamen atlanır."""
    assert _sirket_varlik_sinifi_uygunluk_disi_mi("ASELS", None) is None


def test_bilinmeyen_ticker_sessizce_atlanir():
    """`SPEC_BY_SYMBOL`'de karşılığı olmayan tickerlardan biri (bkz. modül
    docstring'i, ~14/126 ticker'ın karşılığı yok) — sınıf bilinmiyor,
    uydurma yok, kontrol sessizce atlanır."""
    assert _sirket_varlik_sinifi_uygunluk_disi_mi("BOYLE-BIR-SEMBOL-YOK", 1) is None


# ---------------------------------------------------------------------------
# _uygunluk_blogu
# ---------------------------------------------------------------------------


def test_uygunluk_blogu_baslik_ve_sinifi_icerir():
    metin = _uygunluk_blogu("Hisse Senedi")

    assert "Risk profili uyumu" in metin
    assert "Hisse Senedi" in metin
    # Uyarı dili DEĞİL, bilgilendirme (bkz. agents/risk_agent.py Yol B ile
    # aynı ilke).
    assert "öneri ya da uyarı değildir" in metin


# ---------------------------------------------------------------------------
# _fetch_risk_survey_score — sahte MCP sunucusu (bkz. tests/
# test_portfolio_agent_tools.py'deki aynı desen; `fastmcp.Client` bir
# `FastMCP` nesnesini doğrudan bellek-içi taşıyıcı olarak kabul eder, bu
# yüzden `MarketAgent(mcp_server_url=...)`'e URL yerine sahte sunucu verilir)
# ---------------------------------------------------------------------------


def _ajan(mcp: FastMCP) -> MarketAgent:
    return MarketAgent(mcp_server_url=mcp)


async def test_fetch_risk_survey_score_basarili():
    mcp = FastMCP("sahte-piyasa")

    @mcp.tool(name="get_user_risk_survey")
    def _risk_survey(user_id: str) -> dict:
        return {"success": True, "data": {"risk_survey_score": 3, "risk_profile": "balanced"}}

    skor = await _ajan(mcp)._fetch_risk_survey_score("kullanici-1")

    assert skor == 3


async def test_fetch_risk_survey_score_basarisizsa_none_doner():
    """Tool `success: false` dönerse (ör. kullanıcı bulunamadı) kontrol
    sessizce ATLANIR — uydurma yok."""
    mcp = FastMCP("basarisiz")

    @mcp.tool(name="get_user_risk_survey")
    def _risk_survey(user_id: str) -> dict:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "yok"}}

    skor = await _ajan(mcp)._fetch_risk_survey_score("kullanici-1")

    assert skor is None


async def test_fetch_risk_survey_score_baglanti_hatasinda_none_doner():
    """Bağlantı/çağrı istisnası ana akışı düşürmemeli — sessizce `None`."""
    mcp = FastMCP("patlayan-anket")

    @mcp.tool(name="get_user_risk_survey")
    def _risk_survey(user_id: str) -> dict:
        raise RuntimeError("kasitli")

    skor = await _ajan(mcp)._fetch_risk_survey_score("kullanici-1")

    assert skor is None
