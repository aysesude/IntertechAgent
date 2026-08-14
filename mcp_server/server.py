"""MCP sunucusu giriş noktası.

Ajanlar veriye asla doğrudan erişmez; tüm veri erişimi buradaki tool'lar
üzerinden, onlar da app/services katmanı üzerinden olur.

Kullanım: python -m mcp_server.server
"""

from fastmcp import FastMCP

from app.core.config import settings
from mcp_server.tools import market_tools, portfolio_tools

mcp = FastMCP("Akıllı Kişisel Finans Danışmanı MCP Server")

portfolio_tools.register(mcp)
market_tools.register(mcp)

# TODO: risk_tools.get_risk_assessment uygulandığında burada register edilecek.


if __name__ == "__main__":
    mcp.run(transport="http", host=settings.mcp_server_host, port=settings.mcp_server_port)
