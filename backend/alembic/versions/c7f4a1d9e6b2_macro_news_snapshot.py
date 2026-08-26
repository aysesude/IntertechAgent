"""macro_news_snapshot tablosu

Canlı makro haber önbelleği (Döviz + Kıymetli Maden, yfinance haber akışı) —
bkz. app/models/macro_news_snapshot.py modül docstring'i (neden bu tablo var,
neden RAG değil, neden istek anında değil batch).

Revision ID: c7f4a1d9e6b2
Revises: b26e8dab6ef9
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7f4a1d9e6b2"
down_revision: str | None = "b26e8dab6ef9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# asset_class_enum zaten 'assets' tablosu için oluşturuldu (bkz. ilk migration
# + 9c31e7a0d2b4); burada yeniden CREATE edilmez, yalnızca kolon tipi olarak
# referans alınır (create_type=False) — 6a92d4c8e0f1'deki price_source_enum
# kullanımıyla aynı kalıp.
asset_class_enum = postgresql.ENUM(name="asset_class_enum", create_type=False)


def upgrade() -> None:
    op.create_table(
        "macro_news_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", asset_class_enum, nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "url", name="uq_macro_news_snapshot_symbol_url"),
    )
    op.create_index(
        "ix_macro_news_snapshot_symbol_published_at",
        "macro_news_snapshot",
        ["symbol", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_macro_news_snapshot_symbol_published_at", table_name="macro_news_snapshot")
    op.drop_table("macro_news_snapshot")
