"""holdings kâr/zarar alanları + data_ingest_log tablosu

- holdings artık defterden türetilen önbellektir: realized_pnl_try satışla
  kilitlenen kâr/zararı taşır (quantity=0 satırları bu yüzden silinmez),
  last_rebuilt_at önbelleğin bayatlığını görünür kılar.
- data_ingest_log: veri toplama işlerinin iş-düzeyi kaydı (AK 5.2/5.3) —
  "dün gece TCMB çekimi başarısız oldu" bilgisi hiçbir fiyat satırında
  görünmez, burada görünür.

Revision ID: 6a92d4c8e0f1
Revises: d17f3b9e5c28
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6a92d4c8e0f1"
down_revision: str | None = "d17f3b9e5c28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

price_source_enum = postgresql.ENUM(name="price_source_enum", create_type=False)
ingest_status_enum = postgresql.ENUM(
    "success", "partial", "failed", "skipped", name="ingest_status_enum", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "holdings",
        sa.Column("realized_pnl_try", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    op.add_column(
        "holdings",
        sa.Column(
            "last_rebuilt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.alter_column(
        "holdings",
        "avg_cost_price",
        type_=sa.Numeric(18, 6),
        existing_type=sa.Numeric(18, 4),
        existing_nullable=False,
    )

    ingest_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "data_ingest_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", price_source_enum, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("status", ingest_status_enum, nullable=False),
        sa.Column("rows_upserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_data_ingest_log_provider_run_at", "data_ingest_log", ["provider", "run_at"]
    )
    op.create_index(
        "ix_data_ingest_log_asset_run_at", "data_ingest_log", ["asset_id", "run_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_data_ingest_log_asset_run_at", table_name="data_ingest_log")
    op.drop_index("ix_data_ingest_log_provider_run_at", table_name="data_ingest_log")
    op.drop_table("data_ingest_log")
    ingest_status_enum.drop(op.get_bind(), checkfirst=True)

    op.alter_column(
        "holdings",
        "avg_cost_price",
        type_=sa.Numeric(18, 4),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )
    op.drop_column("holdings", "last_rebuilt_at")
    op.drop_column("holdings", "realized_pnl_try")
