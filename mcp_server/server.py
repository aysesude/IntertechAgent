"""MCP sunucusu giriş noktası.

Ajanlar veriye asla doğrudan erişmez; tüm veri erişimi buradaki tool'lar
üzerinden, onlar da app/services katmanı üzerinden olur.

Yeni bir tool modülü eklerken tek yapılacak: `_TOOL_MODULES` listesine eklemek.
Modülün `register(mcp)` fonksiyonu kaydettiği tool adlarını döndürür; başlangıç
logunda hangi tool'ların ayakta olduğu görünür ("tool görünmüyor" hatalarının
çoğu kayıt unutmaktan çıkıyor).

Sözleşme: docs/MCP-TOOLS.md · Kullanım: python -m mcp_server.server
"""

import logging

from fastmcp import FastMCP

from app.core.config import settings
from app.core.logging import setup_logging
from mcp_server.tools import market_tools, portfolio_tools

# API süreci bunu app/main.py'de yapıyor; MCP sunucusu ayrı bir süreç olduğu
# için kendi logging kurulumunu kendi yapmalı, yoksa tool logları görünmez.
setup_logging()

logger = logging.getLogger(__name__)

# TODO: risk_tools.get_risk_assessment uygulandığında listeye eklenecek.
_TOOL_MODULES = [portfolio_tools, market_tools]


def register_all(mcp: FastMCP) -> list[str]:
    """Tüm tool modüllerini kaydeder ve kayıtlı tool adlarını döndürür."""
    names: list[str] = []
    for module in _TOOL_MODULES:
        names.extend(module.register(mcp) or [])
    logger.info("[MCP] %d tool kayitli: %s", len(names), ", ".join(sorted(names)) or "-")
    return names


mcp = FastMCP("Akıllı Kişisel Finans Danışmanı MCP Server")
register_all(mcp)


if __name__ == "__main__":
    mcp.run(transport="http", host=settings.mcp_server_host, port=settings.mcp_server_port)
