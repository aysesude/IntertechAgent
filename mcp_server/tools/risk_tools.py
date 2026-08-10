"""TODO: Risk/Strateji Ajanı için risk değerlendirme tool'u. Risk metriği
tanımları (volatilite, yoğunlaşma eşikleri vb.) kullanıcıyla netleştirilmeden
uygulanmayacak (bkz. app/core/config.py TODO notu)."""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="get_risk_assessment")
    def get_risk_assessment(user_id: UUID) -> dict[str, Any]:
        """Bir kullanıcının portföy riskini değerlendirir ve yeniden dengeleme
        önerisi üretir.

        Args:
            user_id: Risk değerlendirmesi istenen kullanıcının UUID'si.
        """
        raise NotImplementedError("TODO: Risk/Strateji Ajanı henüz uygulanmadı")
