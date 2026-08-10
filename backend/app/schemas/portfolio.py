"""Portföy API'sinin ekip sözleşmesi. Frontend'deki src/types/ altındaki
TypeScript tipleri bu şemayla eşleşmelidir."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.core.config import AssetClass

# Hesaplamalarda hassasiyet kaybını önlemek için Decimal kullanılır, ama JSON'a
# giderken düz sayı (float) olarak serialize edilir — string değil, ki frontend
# doğrudan number olarak tüketebilsin.
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


class GainLoss(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Money
    percent: Money


class AllocationItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_class: AssetClass
    value: Money
    percent: Money


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    total_value: Money
    total_cost_basis: Money
    total_gain_loss: GainLoss
    allocation: list[AllocationItem]
    holdings_count: int
