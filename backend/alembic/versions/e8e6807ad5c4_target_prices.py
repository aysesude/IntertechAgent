"""target_prices tablosu

Analist hedef fiyatı (kurum, tavsiye, hedef fiyat) — bkz.
app/models/target_price.py modül docstring'i (neden RAG değil, neden
kurum başına tek satır/upsert). Kaynak kurum başına şirket kodu bazında
tek kayıt tutulur; ayrı bir zaman serisi DEĞİLDİR.

Revision ID: e8e6807ad5c4
Revises: ddaac4267bba
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8e6807ad5c4"
down_revision: str | None = "ddaac4267bba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "target_prices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("institution", sa.String(length=64), nullable=False),
        sa.Column("recommendation", sa.String(length=16), nullable=False),
        sa.Column("target_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="TRY"),
        sa.Column("price_at_report", sa.Numeric(18, 6), nullable=True),
        sa.Column("previous_target_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("revision_direction", sa.String(length=16), nullable=True),
        sa.Column("horizon_months", sa.Integer(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("asset_id", "institution", name="uq_target_prices_asset_institution"),
    )


def downgrade() -> None:
    op.drop_table("target_prices")
