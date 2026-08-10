import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastmcp import Client, FastMCP

from app.core.config import AssetClass
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from mcp_server.tools import portfolio_tools


@pytest.fixture()
def mcp_server():
    mcp = FastMCP("test-finans-mcp")
    portfolio_tools.register(mcp)
    return mcp


@pytest.fixture()
def seeded_user(db_session):
    user = User(email="mcp-test@example.com", full_name="MCP Test User")
    asset = Asset(symbol="MCPT", name="MCP Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add_all([user, asset])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(asset_id=asset.id, price_date=date(2026, 1, 1), close_price=Decimal("42.00")),
            Holding(portfolio_id=portfolio.id, asset_id=asset.id, quantity=Decimal("3"), avg_cost_price=Decimal("40.00")),
        ]
    )
    db_session.commit()
    return user


async def test_get_portfolio_summary_tool_success(mcp_server, seeded_user):
    # portfolio_tools kendi SessionLocal()'ini acar; conftest'in DATABASE_URL'i
    # ayarladigi ayni test DB'sine baglanir (bkz. app/core/db.py).
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_portfolio_summary", {"user_id": str(seeded_user.id)})

    assert result.structured_content["success"] is True
    data = result.structured_content["data"]
    assert data["holdings_count"] == 1
    assert data["total_value"] == 126.0  # 3 * 42.00
    assert data["user_id"] == str(seeded_user.id)


async def test_get_portfolio_summary_tool_not_found(mcp_server, db_session):
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_portfolio_summary", {"user_id": str(uuid.uuid4())})

    assert result.structured_content["success"] is False
    assert result.structured_content["error"]["code"] == "PORTFOLIO_NOT_FOUND"


async def test_get_portfolio_summary_tool_rejects_invalid_uuid(mcp_server):
    with pytest.raises(Exception):  # noqa: B017 - fastmcp ValidationError'i disariya farkli tiplerde sizdirabiliyor
        async with Client(mcp_server) as client:
            await client.call_tool("get_portfolio_summary", {"user_id": "not-a-uuid"})
