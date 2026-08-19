import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastmcp import Client, FastMCP

from app.core.config import AssetClass, RiskProfile
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from mcp_server.tools import risk_tools


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
    # risk_tools kendi SessionLocal()'ini acar; conftest'in DATABASE_URL'i
    # ayarladigi ayni test DB'sine baglanir (bkz. app/core/db.py).
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
    assert result.structured_content["error"]["code"] == "RISK_TARGET_NOT_FOUND"
