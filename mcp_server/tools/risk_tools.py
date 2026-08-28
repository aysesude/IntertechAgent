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
from app.services.user_service import get_and_consume_risk_survey_event, get_user_risk_survey
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

    @mcp.tool(name="get_risk_survey_event")
    @tool_handler()
    def get_risk_survey_event(user_id: UUID) -> dict[str, Any]:
        """Kullanıcının anketi YENİDEN doldurup doldurmadığını (bekleyen bir
        "anket olayı" olup olmadığını) okur — Sinyal 5'in (profil_sapmasi,
        Yol A) TEK girdisi. bkz. docs/notes/
        sinyal5-olay-tabanli-aktivasyon-tasarimi.md.

        BU ÇAĞRI YAN ETKİLİDİR: olay varsa (`olay_var: true`) aynı çağrı
        içinde ATOMİK olarak "tüketilmiş" işaretlenir — bir SONRAKİ çağrıda
        anket tekrar güncellenmediği sürece `olay_var: false` döner. Bu bir
        risk verisi DEĞİŞİKLİĞİ değildir (anket puanı ya da profil hiç
        dokunulmaz), yalnızca "bu olay bir değerlendirmeye gösterildi"
        bayrağıdır — `agents/scope.yaml`'ın "ajan kullanıcının risk verisini
        asla değiştiremez" kuralıyla çelişmez.

        Bu yüzden bu tool'u SADECE fiilen bir risk değerlendirmesi
        üretilirken çağır (ör. `get_risk_assessment` ile birlikte, aynı
        değerlendirme turunda) — meraktan/deneme amaçlı tekrar tekrar
        çağırmak olayı gerçek değerlendirmesi gelmeden "tüketir" ve Sinyal
        5'in kullanıcıya hiç gösterilmemesine yol açar.

        Args:
            user_id: Anket olayı sorgulanacak kullanıcının UUID'si.

        Returns:
            Başarılı: {"success": true, "data": {"olay_var": bool,
            "yeni_profil": str | null, "izin_verilmeyen_ve_elde_olan_siniflar":
            [str, ...]}}. `olay_var=false` ise diğer alanlar anlamsızdır
            (varsayılan değerleriyle gelir), kullanılmamalıdır.
            Hata: {"success": false, "error": {"code": "NOT_FOUND",
            "message": "..."}} — kullanıcı bulunamazsa.
        """
        with db_session() as db:
            event = get_and_consume_risk_survey_event(db, user_id)
            return event.model_dump(mode="json")

    @mcp.tool(name="get_user_risk_survey")
    @tool_handler()
    def get_user_risk_survey_tool(user_id: UUID) -> dict[str, Any]:
        """Kullanıcının GÜNCEL anket puanını ve ondan türeyen profili okur —
        yan etkisiz, salt okunur (bkz. `app/services/user_service.py` modül
        docstring'i "2026-08-28 eki").

        `get_risk_assessment` de aynı alanı taşıyor ama tam bir volatilite/
        VaR hesaplaması yapar; yalnızca puana/profile ihtiyaç duyan bir
        çağıran (ör. `agents/portfolio_agent.py`'nin profil-uyumu kontrolü)
        için bu, tek satırlık ucuz bir alternatiftir — gereksiz yere ağır
        tool'u tetiklemez.

        Args:
            user_id: Anket puanı sorgulanacak kullanıcının UUID'si.

        Returns:
            Başarılı: {"success": true, "data": {"risk_survey_score":
            int | null, "risk_profile": str, "score_band": [int, int] | null,
            "score_min": int, "score_max": int}}. `risk_survey_score=null`
            ise kullanıcı anketi hiç doldurmamıştır — uygunluk/profil-uyumu
            kontrolü bu durumda ATLANMALIDIR (uydurma yok).
            Hata: {"success": false, "error": {"code": "NOT_FOUND",
            "message": "..."}} — kullanıcı bulunamazsa.
        """
        with db_session() as db:
            survey = get_user_risk_survey(db, user_id)
            return survey.model_dump(mode="json")

    return ["get_risk_assessment", "get_risk_survey_event", "get_user_risk_survey"]
