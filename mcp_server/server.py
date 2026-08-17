"""MCP sunucusu giriş noktası.

Ajanlar veriye asla doğrudan erişmez; tüm veri erişimi buradaki tool'lar
üzerinden, onlar da app/services katmanı üzerinden olur.

Kullanım: python -m mcp_server.server
"""

from fastmcp import FastMCP

from app.core.config import settings
from mcp_server.tools import market_tools, portfolio_tools, risk_tools

mcp = FastMCP("Akıllı Kişisel Finans Danışmanı MCP Server")

portfolio_tools.register(mcp)
market_tools.register(mcp)
risk_tools.register(mcp)


if __name__ == "__main__":
    mcp.run(transport="http", host=settings.mcp_server_host, port=settings.mcp_server_port)
