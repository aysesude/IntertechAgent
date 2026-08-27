"""Portföy Ajanı ile MCP tool imzaları arasındaki sözleşme.

NEDEN VAR. Ajan, plandaki HER tool çağrısına `user_id` ekliyordu. Bu, tool'ların
tamamı kullanıcıya bağlıyken doğruydu; `get_asset_price_history` eklendiğinde
bozuldu. O tool portföyden bağımsız piyasa verisi döndürür ve imzasında
`user_id` yoktur — fastmcp tanımadığı argümanı doğrulama hatasıyla reddediyor,
yani tool seçildiği HER seferde çağrı düşüyordu. Üstelik istisna metni
`str(exc)` olarak hata zarfına konuyor, hiçbir ajan başarılı olmadığında
`orchestrator.merge_responses` onu doğrudan kullanıcıya akıtıyordu: ekranda ham
bir pydantic doğrulama hatası.

Mevcut testler bunu göremezdi; `test_portfolio_agent_plan.py` yalnızca
`_parse_plan`'i (metin → plan) sınıyor, çağrının kendisini hiç yapmıyor.

Buradaki ilk test kasıtlı olarak GERÇEK tool imzalarına bakıyor: `TOOLS`'a yeni
bir ad eklenip `_USER_SCOPED_TOOLS` güncellenmezse test kendini hatırlatır.
"""

import pytest
from fastmcp import Client, FastMCP

from agents.portfolio_agent import (
    _CLIENT_ERROR_MESSAGE,
    _RESULT_KEY,
    _USER_SCOPED_TOOLS,
    TOOLS,
    PortfolioAgent,
)
from mcp_server.tools import portfolio_tools, price_tools


def _ajan() -> PortfolioAgent:
    # Adres kullanılmıyor: testler `_run_plan`'e hazır bir istemci veriyor.
    return PortfolioAgent(mcp_server_url="http://kullanilmiyor")


# ---------------------------------------------------------------------------
# Sözleşme: hangi tool user_id ister?
# ---------------------------------------------------------------------------


@pytest.fixture()
def mcp_server():
    mcp = FastMCP("test-portfolio-mcp")
    portfolio_tools.register(mcp)
    price_tools.register(mcp)
    return mcp


async def test_user_id_kumesi_gercek_tool_imzalariyla_uyusuyor(mcp_server):
    """`_USER_SCOPED_TOOLS`, tool'ların gerçek şemasıyla birebir örtüşmeli.

    Elle tutulan bir liste sessizce eskir; bu test onu sunucudaki imzaya
    bağlıyor. Kırılırsa mesaj hangi yönde saptığını söyler.
    """
    async with Client(mcp_server) as client:
        semalar = {tool.name: (tool.inputSchema or {}) for tool in await client.list_tools()}

    for name in TOOLS:
        assert name in semalar, f"{name} MCP sunucusunda kayıtlı değil"
        imza_ister = "user_id" in (semalar[name].get("properties") or {})
        kume_iceriyor = name in _USER_SCOPED_TOOLS
        assert imza_ister == kume_iceriyor, (
            f"{name}: imza user_id {'istiyor' if imza_ister else 'İSTEMİYOR'} ama "
            f"_USER_SCOPED_TOOLS {'içeriyor' if kume_iceriyor else 'İÇERMİYOR'}"
        )


def test_her_toolun_sonuc_anahtari_var():
    """`_RESULT_KEY`'de karşılığı olmayan bir tool `execute`'ta KeyError atar ve
    yalnızca ajanı değil tüm sohbeti düşürür."""
    assert set(TOOLS) == set(_RESULT_KEY)


# ---------------------------------------------------------------------------
# Davranış: enjeksiyon ve hata zarfı
# ---------------------------------------------------------------------------


@pytest.fixture()
def sahte_sunucu():
    """Gerçek tool'ların imza SÖZLEŞMESİNİ taklit eden, DB'siz sunucu.

    Gördüğü argümanları `gorulen`e yazar; testler enjeksiyonun hangi tool'a
    gidip hangisine gitmediğini buradan okur.
    """
    mcp = FastMCP("sahte")
    gorulen: dict[str, dict] = {}

    @mcp.tool(name="get_holdings")
    def _holdings(user_id: str) -> dict:
        """Kullanıcıya bağlı tool."""
        gorulen["get_holdings"] = {"user_id": user_id}
        return {"success": True, "data": {"holdings": []}}

    @mcp.tool(name="get_asset_price_history")
    def _price_history(symbols: list[str], window: str = "3m") -> dict:
        """Kullanıcıdan BAĞIMSIZ tool — user_id kabul etmez."""
        gorulen["get_asset_price_history"] = {"symbols": symbols, "window": window}
        return {"success": True, "data": {"series": {}}}

    return mcp, gorulen


async def test_kullanicidan_bagimsiz_tool_user_id_almaz(sahte_sunucu):
    """Regresyon: `get_asset_price_history` çağrısı her seferinde düşüyordu.

    Ölçüldü: fastmcp 3.4.6 tanımadığı argüman için `ToolError`
    (`unexpected_keyword_argument`) fırlatıyor.
    """
    mcp, gorulen = sahte_sunucu
    plan = [("get_holdings", {}), ("get_asset_price_history", {"symbols": ["XAUTRY"]})]

    async with Client(mcp) as client:
        sonuc = await _ajan()._run_plan(client, plan, "kullanici-1")

    # Kullanıcıya bağlı tool user_id'yi ALIR...
    assert gorulen["get_holdings"] == {"user_id": "kullanici-1"}
    # ...bağımsız olan ALMAZ ve çağrı başarıyla döner.
    assert gorulen["get_asset_price_history"] == {"symbols": ["XAUTRY"], "window": "3m"}
    assert sonuc["get_asset_price_history"]["success"] is True


async def test_modelin_yazdigi_user_id_ezilir(sahte_sunucu):
    """Güvenlik: model başka bir kullanıcının verisini isteyemez.

    `_parse_plan` zaten `user_id`'yi eliyor; bu, ikinci savunma hattının da
    yerinde olduğunu gösterir (plan başka bir yoldan gelse bile).
    """
    mcp, gorulen = sahte_sunucu

    async with Client(mcp) as client:
        await _ajan()._run_plan(
            client, [("get_holdings", {"user_id": "baskasinin-uuid"})], "kullanici-1"
        )

    assert gorulen["get_holdings"] == {"user_id": "kullanici-1"}


async def test_ic_hata_metni_kullaniciya_gitmez():
    """İç hata gizliliği (CLAUDE.md §4).

    `_run_plan`'in hata zarfı doğrudan `AgentResponse.error`'a, oradan hiçbir
    ajan başarılı olmadığında kullanıcının ekranına gidiyor. İstisna metni
    bağlantı dizesi, SQL ya da kütüphane izi taşıyabilir.
    """
    mcp = FastMCP("patlayan")

    @mcp.tool(name="get_holdings")
    def _holdings(user_id: str) -> dict:
        """Patlayan tool."""
        raise RuntimeError("postgresql://kullanici:GIZLI_PAROLA@db:5432/finans")

    async with Client(mcp) as client:
        sonuc = await _ajan()._run_plan(client, [("get_holdings", {})], "kullanici-1")

    mesaj = sonuc["get_holdings"]["error"]["message"]
    assert mesaj == _CLIENT_ERROR_MESSAGE
    assert "GIZLI_PAROLA" not in mesaj
    assert "postgresql" not in mesaj


async def test_bir_tool_patlarsa_digeri_yine_doner(sahte_sunucu):
    """Zarif düşüş: tek tool hatası ajanı düşürmemeli."""
    mcp, _ = sahte_sunucu

    @mcp.tool(name="get_portfolio_summary")
    def _summary(user_id: str) -> dict:
        """Patlayan tool."""
        raise RuntimeError("kasitli")

    plan = [("get_portfolio_summary", {}), ("get_holdings", {})]
    async with Client(mcp) as client:
        sonuc = await _ajan()._run_plan(client, plan, "kullanici-1")

    assert sonuc["get_portfolio_summary"]["success"] is False
    assert sonuc["get_holdings"]["success"] is True
