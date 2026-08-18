"""Portföy tool'ları. Bu dosya aynı zamanda **referans uygulamadır**: yeni bir
tool yazarken kalıp buradan kopyalanır (bkz. docs/MCP-TOOLS.md).

Kurallar: tool veriye doğrudan erişmez, her zaman app.services üzerinden okur;
sayısal hiçbir değer burada hesaplanmaz; zarfı `@tool_handler` kurar, gövde
yalnızca veriyi döndürür.
"""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from app.services.portfolio_service import (
    get_portfolio_summary as fetch_portfolio_summary,
)
from mcp_server.tools._base import db_session, tool_handler


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_portfolio_summary")
    @tool_handler()
    def get_portfolio_summary(user_id: UUID) -> dict[str, Any]:
        """Bir kullanıcının portföyünün tek seferlik özetini döndürür.

        Ne zaman kullanılır: "portföyüm ne durumda", "toplam değerim ne kadar",
        "dağılımım nasıl", "kâr mı zarar mı ettim" gibi bütünsel sorular.

        Ne zaman kullanılmaz: tek tek varlıkların listesi isteniyorsa
        (get_holdings), zaman içindeki performans/geçmiş getiri soruluyorsa
        (get_performance), işlem geçmişi soruluyorsa (get_transactions), risk
        veya yeniden dengeleme soruluyorsa (get_risk_assessment).

        Args:
            user_id: Portföy özeti istenen kullanıcının UUID'si.

        Returns:
            Başarılı: {"success": true, "data": {"user_id": ..., "as_of":
            "2026-08-01", "total_value": 125430.5, "total_cost_basis": ...,
            "total_gain_loss": {"amount": ..., "percent": ...}, "allocation":
            [{"asset_class": "stock", "value": ..., "percent": ...}, ...],
            "holdings_count": 7}}. Tüm tutarlar TRY, sayı (string değil).
            Hata: {"success": false, "error": {"code": "NOT_FOUND",
            "message": "..."}} — kullanıcının portföyü yoksa.
        """
        with db_session() as db:
            return fetch_portfolio_summary(db, user_id).model_dump(mode="json")

    return ["get_portfolio_summary"]
