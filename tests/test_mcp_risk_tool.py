import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastmcp import Client, FastMCP

from app.core.config import AssetClass, RiskProfile
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from app.services.user_service import set_user_risk_survey
from mcp_server.tools import risk_tools
from mcp_server.tools._base import ToolErrorCode


@pytest.fixture()
def mcp_server():
    mcp = FastMCP("test-finans-mcp")
    risk_tools.register(mcp)
    return mcp


@pytest.fixture()
def seeded_user(db_session):
    user = User(
        email="mcp-risk-test@example.com",
        full_name="MCP Risk Test User",
        risk_profile=RiskProfile.BALANCED,
    )
    asset = Asset(
        symbol="MCPT", name="MCP Test Hisse", asset_class=AssetClass.STOCK, currency="TRY"
    )
    db_session.add_all([user, asset])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(
                asset_id=asset.id, price_date=date(2026, 1, 1), close_price=Decimal("42.00")
            ),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=asset.id,
                quantity=Decimal(3),
                avg_cost_price=Decimal("40.00"),
            ),
        ]
    )
    db_session.commit()
    return user


async def test_get_risk_assessment_tool_success(mcp_server, seeded_user):
    # risk_tools `db_session()` (mcp_server/tools/_base.py) uzerinden acar;
    # conftest'in DATABASE_URL'i ayarladigi ayni test DB'sine baglanir
    # (bkz. app/core/db.py).
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_risk_assessment", {"user_id": str(seeded_user.id)})

    assert result.structured_content["success"] is True
    data = result.structured_content["data"]
    assert data["user_id"] == str(seeded_user.id)
    assert data["risk_profile"] == "balanced"
    assert data["risk_profile_source"] == "user"
    assert "disclaimer" in data
    assert "yatırım tavsiyesi" in data["disclaimer"].lower()


async def test_get_risk_assessment_tool_with_profile_override(mcp_server, seeded_user):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "get_risk_assessment",
            {"user_id": str(seeded_user.id), "profile_override": "aggressive"},
        )

    data = result.structured_content["data"]
    assert data["risk_profile"] == "aggressive"
    assert data["risk_profile_source"] == "override"


async def test_get_risk_assessment_tool_not_found(mcp_server, db_session):
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_risk_assessment", {"user_id": str(uuid.uuid4())})

    assert result.structured_content["success"] is False
    # Ozel bir kod degil, ortak taksonomi (bkz. docs/MCP-TOOLS.md, _base.py'deki
    # APP_ERROR_CODE_MAP): NotFoundError.code="NOT_FOUND" otomatik eslenir.
    assert result.structured_content["error"]["code"] == ToolErrorCode.NOT_FOUND.value


# --- get_risk_survey_event (Sinyal 5, Yol A) --------------------------------
#
# bkz. docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md §4.4/§4.7.
# `seeded_user` hiç anket doldurmamış (risk_survey_score=None) başlar; her
# test kendi ihtiyacına göre `set_user_risk_survey` ile bir "olay" üretir.


async def test_get_risk_survey_event_olay_yok(mcp_server, seeded_user):
    """Hiç anket doldurulmamışsa (risk_survey_updated_at=None) bekleyen bir
    olay yoktur — diğer alanlara bakılmamalı."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_risk_survey_event", {"user_id": str(seeded_user.id)})

    assert result.structured_content["success"] is True
    assert result.structured_content["data"]["olay_var"] is False


async def test_get_risk_survey_event_olay_var_ihlal_yok(mcp_server, db_session, seeded_user):
    """Anket yenilendi ve yeni puan (5 -> GROWTH) STOCK (seviye 5) için hâlâ
    yeterliyse (5<=5) — kullanıcının elindeki tek varlık hâlâ izinli, ihlal
    listesi boş olmalı, ama olay yine de "var" sayılmalı."""
    set_user_risk_survey(db_session, seeded_user.id, 5)

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_risk_survey_event", {"user_id": str(seeded_user.id)})

    data = result.structured_content["data"]
    assert data["olay_var"] is True
    assert data["yeni_profil"] == RiskProfile.GROWTH.value
    assert data["izin_verilmeyen_ve_elde_olan_siniflar"] == []


async def test_get_risk_survey_event_olay_var_ihlal_var(mcp_server, db_session, seeded_user):
    """Anket yenilendi VE yeni puan (3 -> BALANCED) artık STOCK'a (seviye 5)
    izin vermiyor, ama kullanıcının elinde hâlâ MCPT (STOCK) var — Sinyal 5
    Yol A'nın tetiklenmesi gereken tam durum budur."""
    set_user_risk_survey(db_session, seeded_user.id, 3)

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_risk_survey_event", {"user_id": str(seeded_user.id)})

    data = result.structured_content["data"]
    assert data["olay_var"] is True
    assert data["izin_verilmeyen_ve_elde_olan_siniflar"] == [AssetClass.STOCK.value]


async def test_get_risk_survey_event_ikinci_cagri_tuketilmis_doner(
    mcp_server, db_session, seeded_user
):
    """Atomik "oku ve tüket": aynı olay bir sonraki değerlendirmede tekrar
    üretilmemeli, aksi hâlde kullanıcıya her sohbet turunda aynı bulgu tekrar
    tekrar gösterilirdi."""
    set_user_risk_survey(db_session, seeded_user.id, 3)

    async with Client(mcp_server) as client:
        ilk = await client.call_tool("get_risk_survey_event", {"user_id": str(seeded_user.id)})
        ikinci = await client.call_tool("get_risk_survey_event", {"user_id": str(seeded_user.id)})

    assert ilk.structured_content["data"]["olay_var"] is True
    assert ikinci.structured_content["data"]["olay_var"] is False


# --- get_user_risk_survey (agents/portfolio_agent.py'nin profil-uygunluk
# kontrolü için) --------------------------------------------------------------
#
# bkz. `backend/app/services/user_service.py` modül docstring'i "2026-08-28
# eki": bu, `get_risk_survey_event`'in aksine YAN ETKİSİZ, salt okunur bir
# tool — çağrı sayısı sonucu hiç etkilemez.


async def test_get_user_risk_survey_anket_doldurulmamis(mcp_server, seeded_user):
    """`seeded_user` hiç anket doldurmamış — `risk_survey_score` `null`,
    ama `risk_profile` (kayıtlı varsayılan) yine de dolu dönmeli."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_user_risk_survey", {"user_id": str(seeded_user.id)})

    assert result.structured_content["success"] is True
    data = result.structured_content["data"]
    assert data["risk_survey_score"] is None
    assert data["risk_profile"] == RiskProfile.BALANCED.value


async def test_get_user_risk_survey_anket_doldurulmus(mcp_server, db_session, seeded_user):
    set_user_risk_survey(db_session, seeded_user.id, 6)

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_user_risk_survey", {"user_id": str(seeded_user.id)})

    data = result.structured_content["data"]
    assert data["risk_survey_score"] == 6
    assert data["risk_profile"] == RiskProfile.AGGRESSIVE.value


async def test_get_user_risk_survey_yan_etkisiz(mcp_server, db_session, seeded_user):
    """`get_risk_survey_event`'ten FARKI: tekrar tekrar çağrılması hiçbir
    şeyi "tüketmez" — art arda iki çağrı aynı sonucu döner."""
    set_user_risk_survey(db_session, seeded_user.id, 3)

    async with Client(mcp_server) as client:
        ilk = await client.call_tool("get_user_risk_survey", {"user_id": str(seeded_user.id)})
        ikinci = await client.call_tool("get_user_risk_survey", {"user_id": str(seeded_user.id)})

    assert ilk.structured_content["data"] == ikinci.structured_content["data"]


async def test_get_user_risk_survey_tool_not_found(mcp_server, db_session):
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_user_risk_survey", {"user_id": str(uuid.uuid4())})

    assert result.structured_content["success"] is False
    assert result.structured_content["error"]["code"] == ToolErrorCode.NOT_FOUND.value
