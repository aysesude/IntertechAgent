"""get_risk_assessment MCP tool'u. Veriye doğrudan erişmez; her zaman
app.services.risk_service üzerinden okur. Sayısal hiçbir değer burada
hesaplanmaz, servis katmanından geldiği gibi döner.

Risk eşikleri, ağırlıklar ve hedef dağılımlar app/core/config.py'de
tanımlıdır."""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from app.core.config import RiskProfile
from app.core.db import SessionLocal
from app.core.exceptions import NotFoundError
from app.services.risk_service import get_risk_assessment as fetch_risk_assessment


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="get_risk_assessment")
    def get_risk_assessment(
        user_id: UUID, profile_override: RiskProfile | None = None
    ) -> dict[str, Any]:
        """Bir kullanıcının portföy riskini değerlendirir ve yeniden dengeleme
        önerisi üretir. Risk skoru (0-100), risk etiketi (düşük/orta/yüksek),
        yıllıklandırılmış volatilite, korelasyon matrisi, kovaryans tabanlı
        portföy volatilitesi, VaR (Value at Risk), Sharpe oranı, yoğunlaşma
        ve çeşitlendirme metrikleri ile varlık sınıfı bazlı alım/satım
        önerisi döndürür. Tüm sayısal değerler veritabanından hesaplanır;
        LLM tarafından üretilmez.

        Args:
            user_id: Risk değerlendirmesi istenen kullanıcının UUID'si.
            profile_override: Verilirse hesaplama bu risk profiline göre
                yapılır (conservative | balanced | aggressive). Kullanıcının
                kayıtlı profili değişmez — "ya agresif olsaydım?" senaryosu
                içindir. Verilmezse kullanıcının kayıtlı profili kullanılır.

        Returns:
            Başarılıysa {"success": true, "data": {...risk değerlendirmesi...}}.
            Kullanıcı ya da portföy bulunamazsa
            {"success": false, "error": {"code": ..., "message": ...}}.
        """
        db = SessionLocal()
        try:
            assessment = fetch_risk_assessment(db, user_id, profile_override)
            return {"success": True, "data": assessment.model_dump(mode="json")}
        except NotFoundError as exc:
            return {
                "success": False,
                "error": {"code": "RISK_TARGET_NOT_FOUND", "message": exc.message},
            }
        finally:
            db.close()
