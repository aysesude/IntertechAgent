"""get_portfolio_summary MCP tool'u. Veriye doğrudan erişmez; her zaman
app.services.portfolio_service üzerinden okur. Sayısal hiçbir değer burada
hesaplanmaz, servis katmanından geldiği gibi döner."""

from typing import Any
from uuid import UUID

from app.core.db import SessionLocal
from app.core.exceptions import NotFoundError
from app.services.portfolio_service import (
    get_portfolio_summary as fetch_portfolio_summary,
)
from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="get_portfolio_summary")
    def get_portfolio_summary(user_id: UUID) -> dict[str, Any]:
        """Bir kullanıcının portföy özetini döndürür: toplam değer, varlık sınıfı
        bazlı yüzdesel dağılım ve toplam kâr/zarar. Tüm sayısal değerler
        veritabanından gelir; LLM tarafından üretilmez.

        Args:
            user_id: Portföy özeti istenen kullanıcının UUID'si.

        Returns:
            Başarılıysa {"success": true, "data": {...portföy özeti...}}.
            Kullanıcının portföyü yoksa {"success": false, "error": {"code": ..., "message": ...}}.
        """
        db = SessionLocal()
        try:
            summary = fetch_portfolio_summary(db, user_id)
            return {"success": True, "data": summary.model_dump(mode="json")}
        except NotFoundError as exc:
            return {
                "success": False,
                "error": {"code": "PORTFOLIO_NOT_FOUND", "message": exc.message},
            }
        finally:
            db.close()
