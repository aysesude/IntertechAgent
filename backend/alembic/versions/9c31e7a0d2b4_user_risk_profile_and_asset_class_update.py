"""users.risk_profile + asset_class enum: gold -> precious_metal, + cash

gerek.md §2 beş varlık sınıfı tanımlar: hisse, kıymetli maden, döviz, tahvil,
nakit. 'gold' sınıfı gümüş/platini de kapsayacak şekilde 'precious_metal'
olur; 'cash' (vadeli/vadesiz mevduat) eklenir. risk_profile, seed'in farklı
yatırımcı profilleri üretebilmesi ve kişiselleştirme için gerekir.

(Not: Bu içerik daha önce rafa kalkan ck_risk dalında c7a1f2d43b09 +
d3b8e1a95f42 olarak vardı; burada tek migration olarak yeniden yazıldı.)

Revision ID: 9c31e7a0d2b4
Revises: abe38b185ff1
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c31e7a0d2b4"
down_revision: str | None = "abe38b185ff1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

risk_profile_enum = postgresql.ENUM(
    "conservative", "balanced", "aggressive", name="risk_profile_enum", create_type=False
)


def upgrade() -> None:
    risk_profile_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "risk_profile", risk_profile_enum, server_default="balanced", nullable=False
        ),
    )

    # RENAME VALUE transaction içinde güvenlidir ve mevcut satırları da günceller.
    op.execute("ALTER TYPE asset_class_enum RENAME VALUE 'gold' TO 'precious_metal'")
    # ADD VALUE de transaction içinde çalışır; kısıt yalnızca yeni değerin AYNI
    # transaction'da KULLANILAMAMASIDIR. Bu migration 'cash' kullanmaz.
    op.execute("ALTER TYPE asset_class_enum ADD VALUE IF NOT EXISTS 'cash'")


def downgrade() -> None:
    op.execute("ALTER TYPE asset_class_enum RENAME VALUE 'precious_metal' TO 'gold'")
    # PG enum'dan değer silemez; tip yeniden yaratılır ('cash' satırı olmadığı
    # varsayımıyla — varsa önce elle taşınmalı).
    op.execute("ALTER TYPE asset_class_enum RENAME TO asset_class_enum_old")
    op.execute("CREATE TYPE asset_class_enum AS ENUM ('stock','gold','currency','bond')")
    op.execute(
        "ALTER TABLE assets ALTER COLUMN asset_class TYPE asset_class_enum "
        "USING asset_class::text::asset_class_enum"
    )
    op.execute("DROP TYPE asset_class_enum_old")

    op.drop_column("users", "risk_profile")
    risk_profile_enum.drop(op.get_bind(), checkfirst=True)
