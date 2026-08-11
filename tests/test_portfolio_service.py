import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.config import AssetClass
from app.core.exceptions import NotFoundError
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from app.services.portfolio_service import get_portfolio_summary


def test_get_portfolio_summary_computes_value_allocation_and_gain(db_session):
    user = User(email="test@example.com", full_name="Test User")
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    gold = Asset(symbol="TAU", name="Test Altin", asset_class=AssetClass.GOLD, currency="TRY")
    db_session.add_all([user, stock, gold])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 1), close_price=Decimal("90.00")
            ),
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 2), close_price=Decimal("100.00")
            ),
            PriceHistory(
                asset_id=gold.id, price_date=date(2026, 1, 1), close_price=Decimal("50.00")
            ),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                quantity=Decimal(10),
                avg_cost_price=Decimal("90.00"),
            ),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=gold.id,
                quantity=Decimal(5),
                avg_cost_price=Decimal("60.00"),
            ),
        ]
    )
    db_session.commit()

    summary = get_portfolio_summary(db_session, user.id)

    assert summary.holdings_count == 2
    # stock: 10 * en guncel fiyat (100.00) = 1000; gold: 5 * 50.00 = 250
    assert summary.total_value == Decimal("1250.00")
    # stock cost: 10*90=900; gold cost: 5*60=300
    assert summary.total_cost_basis == Decimal("1200.00")
    assert summary.total_gain_loss.amount == Decimal("50.00")
    assert summary.total_gain_loss.percent == Decimal("4.17")  # 50/1200*100, 2 ondalik

    allocation_by_class = {item.asset_class: item for item in summary.allocation}
    assert allocation_by_class[AssetClass.STOCK].value == Decimal("1000.00")
    assert allocation_by_class[AssetClass.STOCK].percent == Decimal("80.00")
    assert allocation_by_class[AssetClass.GOLD].value == Decimal("250.00")
    assert allocation_by_class[AssetClass.GOLD].percent == Decimal("20.00")

    # en guncel fiyatin tarihi (stock icin 2 Ocak) as_of olarak yansimali
    assert summary.as_of == date(2026, 1, 2)


def test_get_portfolio_summary_raises_not_found_for_unknown_user(db_session):
    with pytest.raises(NotFoundError):
        get_portfolio_summary(db_session, uuid.uuid4())
