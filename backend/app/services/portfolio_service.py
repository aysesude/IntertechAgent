"""Portföy ile ilgili tüm SQL sorguları burada. API katmanı ve MCP tool'ları
bu modülü çağırır, kendileri sorgu yazmaz."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import AssetClass, settings
from app.core.exceptions import NotFoundError
from app.models import Holding, Portfolio, PriceHistory
from app.schemas.portfolio import AllocationItem, GainLoss, PortfolioSummary

_TWO_DECIMALS = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _latest_prices(db: Session, asset_ids: list[UUID]) -> dict[UUID, tuple[Decimal, date]]:
    """Verilen varlıklar için en güncel (en son tarihli) kapanış fiyatını döndürür."""
    if not asset_ids:
        return {}

    row_number = (
        func.row_number()
        .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.price_date.desc())
        .label("row_number")
    )
    subquery = (
        select(
            PriceHistory.asset_id,
            PriceHistory.close_price,
            PriceHistory.price_date,
            row_number,
        )
        .where(PriceHistory.asset_id.in_(asset_ids))
        .subquery()
    )
    rows = db.execute(
        select(subquery.c.asset_id, subquery.c.close_price, subquery.c.price_date).where(
            subquery.c.row_number == 1
        )
    ).all()
    return {row.asset_id: (row.close_price, row.price_date) for row in rows}


def get_portfolio_summary(db: Session, user_id: UUID) -> PortfolioSummary:
    portfolio = db.execute(select(Portfolio).where(Portfolio.user_id == user_id)).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )

    latest_prices = _latest_prices(db, [h.asset_id for h in holdings])

    total_value = Decimal("0")
    total_cost_basis = Decimal("0")
    class_values: dict[AssetClass, Decimal] = {}
    as_of_dates: list[date] = []

    for holding in holdings:
        price, price_date = latest_prices.get(holding.asset_id, (holding.avg_cost_price, None))
        market_value = holding.quantity * price
        cost_basis = holding.quantity * holding.avg_cost_price

        total_value += market_value
        total_cost_basis += cost_basis
        class_values[holding.asset.asset_class] = (
            class_values.get(holding.asset.asset_class, Decimal("0")) + market_value
        )
        if price_date is not None:
            as_of_dates.append(price_date)

    gain_amount = total_value - total_cost_basis
    gain_percent = (gain_amount / total_cost_basis * 100) if total_cost_basis > 0 else Decimal("0")

    class_order = {asset_class: i for i, asset_class in enumerate(settings.supported_asset_classes)}
    allocation = [
        AllocationItem(
            asset_class=asset_class,
            value=_round2(value),
            percent=_round2(value / total_value * 100) if total_value > 0 else Decimal("0"),
        )
        for asset_class, value in sorted(class_values.items(), key=lambda kv: class_order[kv[0]])
    ]

    return PortfolioSummary(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        total_value=_round2(total_value),
        total_cost_basis=_round2(total_cost_basis),
        total_gain_loss=GainLoss(amount=_round2(gain_amount), percent=_round2(gain_percent)),
        allocation=allocation,
        holdings_count=len(holdings),
    )
