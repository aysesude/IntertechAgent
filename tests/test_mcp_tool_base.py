"""Ortak tool zemininin (mcp_server/tools/_base.py) testleri.

Buradaki testler tek bir tool'u degil, TUM tool'larin uzerine oturdugu
sozlesmeyi dogrular: zarf, hata taksonomisi, zaman asimi, ic metnin
sizdirilmamasi. Yeni tool yazan kisi bu dosyayi degil, sadece kendi
tool'unun uc testini yazar (bkz. docs/MCP-TOOLS.md).
"""

import asyncio
import threading
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from app.core.exceptions import InsufficientDataError, NotFoundError
from mcp_server.tools._base import (
    DEFAULT_MESSAGES,
    ToolErrorCode,
    ToolFailure,
    ToolPayload,
    tool_handler,
)

# Zarfa asla girmemesi gereken ic metin. Gercek bir baglanti adresi/anahtar
# KULLANILMAZ: CI'daki gitleaks taramasi dosya uzantisindan bagimsiz calisir
# ve boyle bir dizgi PR'i dusururdu (bkz. .github/workflows/ci.yml).
_INTERNAL_TEXT = "ic detay: holdings tablosu kilitli, kullanici=finans_admin"


@pytest.fixture()
def mcp_server():
    """Sozlesmenin tum yollarini tetikleyen yapay tool'lar."""
    mcp = FastMCP("test-tool-base")

    @mcp.tool(name="ok_tool")
    @tool_handler()
    def ok_tool(user_id: str, limit: int = 3) -> dict[str, Any]:
        """Basarili senkron tool."""
        return {"user_id": user_id, "limit": limit, "thread": threading.current_thread().name}

    @mcp.tool(name="payload_tool")
    @tool_handler()
    def payload_tool() -> dict[str, Any]:
        """meta donduren tool."""
        return ToolPayload(data={"price": 42.5}, meta={"source": "tcmb", "as_of": "2026-08-17"})

    @mcp.tool(name="not_found_tool")
    @tool_handler()
    def not_found_tool() -> dict[str, Any]:
        """Servis NotFoundError firlatir."""
        raise NotFoundError("Portfolio not found for user_id 6f1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8")

    @mcp.tool(name="insufficient_tool")
    @tool_handler()
    def insufficient_tool() -> dict[str, Any]:
        """Servis InsufficientDataError firlatir."""
        raise InsufficientDataError("only 12 of 60 required days available")

    @mcp.tool(name="failure_tool")
    @tool_handler()
    def failure_tool() -> dict[str, Any]:
        """Govde beklenen basarisizligi ToolFailure ile bildirir."""
        raise ToolFailure(
            ToolErrorCode.PROVIDER_UNAVAILABLE,
            "Veri kaynagina ulasilamadi.",
            detail=_INTERNAL_TEXT,
        )

    @mcp.tool(name="boom_tool")
    @tool_handler()
    def boom_tool() -> dict[str, Any]:
        """Beklenmeyen istisna."""
        raise RuntimeError(f"connection failed: {_INTERNAL_TEXT}")

    @mcp.tool(name="bad_return_tool")
    @tool_handler()
    def bad_return_tool() -> dict[str, Any]:
        """Sozlesmeye aykiri donus tipi."""
        return "duz metin"

    @mcp.tool(name="slow_tool")
    @tool_handler(timeout=0.2)
    async def slow_tool() -> dict[str, Any]:
        """Zaman asimina ugrayan tool."""
        await asyncio.sleep(5)
        return {"never": True}

    return mcp


async def _call(mcp, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    async with Client(mcp) as client:
        result = await client.call_tool(name, args or {})
    return result.structured_content


async def test_basari_zarfi_data_alanini_her_zaman_icerir(mcp_server):
    envelope = await _call(mcp_server, "ok_tool", {"user_id": "u-1"})

    assert envelope["success"] is True
    # Ajanlar tool_result["data"] diye okuyor; alanin varligi sozlesme geregi.
    assert envelope["data"]["user_id"] == "u-1"
    assert envelope["data"]["limit"] == 3
    assert "error" not in envelope


async def test_senkron_govde_olay_dongusunu_bloklamaz(mcp_server):
    """Senkron govde worker thread'e alinir; ajanlar paralel calismaya
    basladiginda olay dongusu bloklanmasin diye."""
    envelope = await _call(mcp_server, "ok_tool", {"user_id": "u-1"})

    assert envelope["data"]["thread"] != threading.main_thread().name


async def test_meta_alani_yalnizca_istenirse_doner(mcp_server):
    with_meta = await _call(mcp_server, "payload_tool")
    without_meta = await _call(mcp_server, "ok_tool", {"user_id": "u-1"})

    assert with_meta["meta"] == {"source": "tcmb", "as_of": "2026-08-17"}
    assert "meta" not in without_meta


async def test_servis_notfound_hatasi_ortak_koda_esler(mcp_server):
    envelope = await _call(mcp_server, "not_found_tool")

    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.NOT_FOUND.value
    # Servisin ic metni (Ingilizce, UUID'li) kullaniciya gitmez.
    assert "Portfolio not found" not in envelope["error"]["message"]
    assert envelope["error"]["message"] == DEFAULT_MESSAGES[ToolErrorCode.NOT_FOUND]


async def test_ak_5_10_yetersiz_veri_tahmin_uretmeden_bildirilir(mcp_server):
    """AK 5.10 / 5.5: veri yetersizse sistem varsayimla doldurmaz, durumu soyler."""
    envelope = await _call(mcp_server, "insufficient_tool")

    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.INSUFFICIENT_DATA.value
    assert "yeterli veri yok" in envelope["error"]["message"]


async def test_toolfailure_detayi_zarfa_girmez(mcp_server):
    envelope = await _call(mcp_server, "failure_tool")

    assert envelope["error"]["code"] == ToolErrorCode.PROVIDER_UNAVAILABLE.value
    assert envelope["error"]["message"] == "Veri kaynagina ulasilamadi."
    # detail yalnizca loga yazilir; zarfta detail alani hic bulunmaz.
    assert set(envelope["error"]) == {"code", "message"}
    assert _INTERNAL_TEXT not in str(envelope)


async def test_beklenmeyen_istisna_zarf_icinde_doner_ve_metni_sizdirmaz(mcp_server):
    """En riskli yol: istisna tool sinirindan kacarsa yalnizca ajan degil tum
    sohbet duser (fastmcp ToolError -> agent -> orchestrator -> SSE)."""
    envelope = await _call(mcp_server, "boom_tool")

    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value
    assert _INTERNAL_TEXT not in str(envelope)
    assert "RuntimeError" not in envelope["error"]["message"]


async def test_sozlesmeye_aykiri_donus_tipi_internal_error_olur(mcp_server):
    envelope = await _call(mcp_server, "bad_return_tool")

    assert envelope["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value


async def test_zaman_asimi_zarf_icinde_doner(mcp_server):
    envelope = await _call(mcp_server, "slow_tool")

    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.TIMEOUT.value


async def test_arguman_dogrulamasi_tool_govdesine_hic_ulasmaz(mcp_server):
    """Tip/format hatasi pydantic tarafindan zarftan ONCE yakalanir; bu yuzden
    INVALID_ARGUMENT kodu tip hatasi icin degil, 'tipi dogru ama anlami yanlis'
    durumlar icindir (bkz. docs/MCP-TOOLS.md)."""
    with pytest.raises(Exception):  # noqa: B017 - fastmcp hata tipini sabitlemiyor
        async with Client(mcp_server) as client:
            await client.call_tool("ok_tool", {"user_id": "u-1", "limit": "uc-tane"})
