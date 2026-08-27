"""get_risk_assessment MCP tool'u. Veriye doğrudan erişmez; her zaman
app.services.risk_service üzerinden okur. Sayısal hiçbir değer burada
hesaplanmaz, servis katmanından geldiği gibi döner.

Risk eşikleri, ağırlıklar ve hedef dağılımlar app/core/config.py'de
tanımlıdır.

Diğer tool ailelerinin (portfolio_tools, market_tools) izlediği ortak
sözleşme: docs/MCP-TOOLS.md. Zarf ve hata taksonomisi `@tool_handler` ile
kurulur; gövde yalnızca veriyi döndürür — `NotFoundError` (app.core.
exceptions.AppError alt sınıfı, code="NOT_FOUND") `_base.py`'deki
`APP_ERROR_CODE_MAP` üzerinden otomatik `ToolErrorCode.NOT_FOUND`'a
eşlenir, burada ayrıca yakalanmasına gerek yok."""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from app.core.config import RiskProfile
from app.services.risk_service import get_risk_assessment as fetch_risk_assessment
from mcp_server.tools._base import db_session, tool_handler


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_risk_assessment")
    @tool_handler()
    def get_risk_assessment(
        user_id: UUID,
        profile_override: RiskProfile | None = None,
        include_scenarios: bool = False,
    ) -> dict[str, Any]:
        """Bir kullanıcının portföy riskini v2 metodolojisiyle değerlendirir:
        kategori bazlı (Hisse/Altın/Döviz/Tahvil/Nakit) volatilite ve
        korelasyon, yıllık portföy volatilitesinden gelen 7 kademeli risk
        seviyesi, VaR (Value at Risk), Sharpe oranı, yoğunlaşma ve
        çeşitlendirme metrikleri döndürür. Volatilite kullanıcının risk
        profili için beklenen bandın üzerindeyse kök neden teşhisi
        (`causes` — Yoğunlaşma/Yüksek volatiliteli varlık/Korelasyon) de
        eklenir. Tüm sayısal değerler veritabanından hesaplanır; LLM
        tarafından üretilmez.

        Args:
            user_id: Risk değerlendirmesi istenen kullanıcının UUID'si.
            profile_override: Verilirse hesaplama bu risk profiline göre
                yapılır (conservative | balanced | growth | aggressive).
                Kullanıcının kayıtlı profili değişmez — "ya agresif olsaydım?"
                senaryosu içindir. Verilmezse kullanıcının kayıtlı profili
                kullanılır.
            include_scenarios: True verilirse VE volatilite profilin hedef
                bandının üzerindeyse, kural tabanlı (deterministik) yeniden
                dengeleme senaryoları (`scenarios`) da üretilir — hangi
                varlığın alınıp satılacağını, beklenen getiriyi veya fiyat
                tahminini ASLA içermez, yalnızca alternatif bir ağırlık
                dağılımı önerir. Ek hesaplama maliyeti nedeniyle varsayılan
                olarak kapalıdır.

        Returns:
            Başarılı: {"success": true, "data": {...risk değerlendirmesi...}}.
            Hata: {"success": false, "error": {"code": "NOT_FOUND",
            "message": "..."}} — kullanıcı ya da portföyü bulunamazsa.
        """
        with db_session() as db:
            assessment = fetch_risk_assessment(
                db, user_id, profile_override, include_scenarios=include_scenarios
            )
            return assessment.model_dump(mode="json")

    return ["get_risk_assessment"]
