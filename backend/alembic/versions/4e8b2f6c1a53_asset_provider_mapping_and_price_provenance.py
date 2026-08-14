"""assets sağlayıcı eşlemesi + price_history kaynak/zaman damgası

- assets: sub_type, is_active, data_source, provider_symbol,
  derived_from_asset_id, derived_factor. Sağlayıcı eşlemesi kodda değil
  şemada durur: toplama işi hangi varlığı nereden çekeceğini SQL ile bulur,
  varlık eklemek kod değişikliği gerektirmez. AK 5.1 ("yalnızca onaylanmış
  kaynaklar") tek sorguyla denetlenebilir hale gelir.
- price_history: source + fetched_at (AK 5.3 "veri güncelleme zamanı
  tutulacak"). close_price 18,4 -> 18,6: TEFAS fon fiyatları 6 ondalık
  yayımlanıyor; şimdi genişletmek maliyetsiz, sonra genişletmek kaybı geri
  getirmez.

Revision ID: 4e8b2f6c1a53
Revises: 9c31e7a0d2b4
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4e8b2f6c1a53"
down_revision: str | None = "9c31e7a0d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

price_source_enum = postgresql.ENUM(
    "synthetic",
    "derived",
    "yfinance",
    "tefas",
    "isportfoy",
    "tcmb",
    "tcmb_evds",
    name="price_source_enum",
    create_type=False,
)


def upgrade() -> None:
    price_source_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("assets", sa.Column("sub_type", sa.String(length=32), nullable=True))
    op.add_column(
        "assets",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "assets",
        sa.Column("data_source", price_source_enum, server_default="synthetic", nullable=False),
    )
    op.add_column("assets", sa.Column("provider_symbol", sa.String(length=64), nullable=True))
    op.add_column("assets", sa.Column("derived_from_asset_id", sa.Uuid(), nullable=True))
    op.add_column("assets", sa.Column("derived_factor", sa.Numeric(18, 8), nullable=True))
    op.create_foreign_key(
        "fk_assets_derived_from", "assets", "assets", ["derived_from_asset_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_assets_derived_consistency",
        "assets",
        "(data_source = 'derived') = "
        "(derived_from_asset_id IS NOT NULL AND derived_factor IS NOT NULL)",
    )

    op.add_column(
        "price_history",
        sa.Column("source", price_source_enum, server_default="synthetic", nullable=False),
    )
    op.add_column(
        "price_history",
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.alter_column(
        "price_history",
        "close_price",
        type_=sa.Numeric(18, 6),
        existing_type=sa.Numeric(18, 4),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "price_history",
        "close_price",
        type_=sa.Numeric(18, 4),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )
    op.drop_column("price_history", "fetched_at")
    op.drop_column("price_history", "source")

    op.drop_constraint("ck_assets_derived_consistency", "assets", type_="check")
    op.drop_constraint("fk_assets_derived_from", "assets", type_="foreignkey")
    op.drop_column("assets", "derived_factor")
    op.drop_column("assets", "derived_from_asset_id")
    op.drop_column("assets", "provider_symbol")
    op.drop_column("assets", "data_source")
    op.drop_column("assets", "is_active")
    op.drop_column("assets", "sub_type")

    price_source_enum.drop(op.get_bind(), checkfirst=True)
