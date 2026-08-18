import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastmcp import Client, FastMCP
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import AssetClass
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from mcp_server.tools import portfolio_tools
from mcp_server.tools._base import DEFAULT_MESSAGES, ToolErrorCode


@pytest.fixture()
def mcp_server():
    mcp = FastMCP("test-finans-mcp")
    portfolio_tools.register(mcp)
    return mcp


@pytest.fixture()
def seeded_user(db_session):
    user = User(email="mcp-test@example.com", full_name="MCP Test User")
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
    missing_user_id = str(uuid.uuid4())
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_portfolio_summary", {"user_id": missing_user_id})

    envelope = result.structured_content
    assert envelope["success"] is False
    # Ortak taksonomi: alan adina ozel kod (PORTFOLIO_NOT_FOUND) yok.
    assert envelope["error"]["code"] == ToolErrorCode.NOT_FOUND.value
    # Servisin ic metni ("Portfolio not found for user_id <uuid>") kullaniciya
    # gitmez; zarftaki mesaj Turkce ve merkezidir.
    assert missing_user_id not in envelope["error"]["message"]
    assert envelope["error"]["message"] == DEFAULT_MESSAGES[ToolErrorCode.NOT_FOUND]


async def test_get_portfolio_summary_tool_beklenmeyen_hatada_cokmez(mcp_server, monkeypatch):
    """Servis katmani beklenmeyen bir istisna firlatirsa tool zarf doner.
    Istisna tool sinirindan kacsaydi tum SSE akisi duser, asistan mesaji
    INCOMPLETE yazilirdi (bkz. app/api/chat.py)."""

    def patlat(db, user_id):
        raise SQLAlchemyError("connection to server at 10.0.0.1 failed: password authentication")

    monkeypatch.setattr(portfolio_tools, "fetch_portfolio_summary", patlat)

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_portfolio_summary", {"user_id": str(uuid.uuid4())})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value
    assert "password" not in envelope["error"]["message"]


async def test_get_portfolio_summary_tool_rejects_invalid_uuid(mcp_server):
    with pytest.raises(
        Exception
    ):  # noqa: B017 - fastmcp ValidationError'i disariya farkli tiplerde sizdirabiliyor
        async with Client(mcp_server) as client:
            await client.call_tool("get_portfolio_summary", {"user_id": "not-a-uuid"})
