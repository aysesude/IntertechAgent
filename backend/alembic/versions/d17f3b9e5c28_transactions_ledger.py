"""transactions -> gerçek işlem defteri (ledger)

- İşlem tipleri 2 -> 7: buy/sell/deposit/withdraw/dividend/interest/fee.
  DEPOSIT/WITHDRAW olmadan hiçbir getiri hesabı doğru olamaz: 100.000 TL
  yatıran kullanıcının portföy değeri artışı "getiri" değildir (TWR).
- asset_id NULL olabilir (nakit hareketleri varlığa bağlı değildir).
- cash_amount_try: her işlemin işaretli nakit ayağı; nakit bakiyesi =
  SUM(cash_amount_try). fx_rate_to_try: işlem anındaki kur, dondurulur.
- Defter append-only'dir; tek yazma kapısı ledger_service.record_transaction.

Enum genişletmesi ADD VALUE ile DEĞİL tip yeniden yaratmayla yapılır:
ADD VALUE ile eklenen değer aynı transaction'da kullanılamaz, oysa bu
migration'daki CHECK kısıtları yeni değerlere başvurur. Yeniden yaratılan
tipin tüm değerleri hemen kullanılabilir.

Revision ID: d17f3b9e5c28
Revises: 4e8b2f6c1a53
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d17f3b9e5c28"
down_revision: str | None = "4e8b2f6c1a53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum RENAME TO transaction_type_enum_old")
    op.execute(
        "CREATE TYPE transaction_type_enum AS ENUM "
        "('buy','sell','deposit','withdraw','dividend','interest','fee')"
    )
    op.execute(
        "ALTER TABLE transactions ALTER COLUMN transaction_type "
        "TYPE transaction_type_enum USING transaction_type::text::transaction_type_enum"
    )
    op.execute("DROP TYPE transaction_type_enum_old")

    op.alter_column(
        "transactions", "asset_id", existing_type=sa.Uuid(), nullable=True
    )
    # price: nakit hareketlerinde anlamsız -> NULL olabilir; 18,6 hassasiyet.
    op.alter_column(
        "transactions",
        "price",
        type_=sa.Numeric(18, 6),
        existing_type=sa.Numeric(18, 4),
        nullable=True,
    )
    # quantity: mevcut kolonda default yoktu; nakit hareketleri için 0 varsayılanı.
    op.alter_column(
        "transactions",
        "quantity",
        existing_type=sa.Numeric(18, 6),
        server_default="0",
        existing_nullable=False,
    )
    op.add_column(
        "transactions",
        sa.Column("currency", sa.String(length=8), server_default="TRY", nullable=False),
    )
    op.add_column(
        "transactions",
        sa.Column("fx_rate_to_try", sa.Numeric(18, 6), server_default="1", nullable=False),
    )
    op.add_column(
        "transactions",
        sa.Column("fee_try", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    # Mevcut sentetik satırlar 0 ile doldurulur; seed zaten baştan üretilecek
    # (bkz. plan §7.2 — migration veri taşımaz).
    op.add_column(
        "transactions",
        sa.Column("cash_amount_try", sa.Numeric(18, 4), server_default="0", nullable=False),
    )
    op.add_column("transactions", sa.Column("note", sa.String(length=255), nullable=True))

    op.create_check_constraint(
        "ck_transactions_asset_required",
        "transactions",
        "(transaction_type IN ('buy','sell','dividend')) = (asset_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_transactions_quantity_nonneg", "transactions", "quantity >= 0"
    )
    op.create_check_constraint(
        "ck_transactions_fx_positive", "transactions", "fx_rate_to_try > 0"
    )
    op.create_check_constraint(
        "ck_transactions_outflow_sign",
        "transactions",
        "transaction_type NOT IN ('buy','withdraw','fee') OR cash_amount_try <= 0",
    )
    op.create_check_constraint(
        "ck_transactions_inflow_sign",
        "transactions",
        "transaction_type NOT IN ('sell','deposit','dividend','interest') "
        "OR cash_amount_try >= 0",
    )

    op.create_index(
        "ix_transactions_portfolio_date", "transactions", ["portfolio_id", "transaction_date"]
    )
    op.create_index(
        "ix_transactions_portfolio_asset_date",
        "transactions",
        ["portfolio_id", "asset_id", "transaction_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_portfolio_asset_date", table_name="transactions")
    op.drop_index("ix_transactions_portfolio_date", table_name="transactions")

    for name in (
        "ck_transactions_inflow_sign",
        "ck_transactions_outflow_sign",
        "ck_transactions_fx_positive",
        "ck_transactions_quantity_nonneg",
        "ck_transactions_asset_required",
    ):
        op.drop_constraint(name, "transactions", type_="check")

    op.drop_column("transactions", "note")
    op.drop_column("transactions", "cash_amount_try")
    op.drop_column("transactions", "fee_try")
    op.drop_column("transactions", "fx_rate_to_try")
    op.drop_column("transactions", "currency")
    op.alter_column(
        "transactions",
        "quantity",
        existing_type=sa.Numeric(18, 6),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "transactions",
        "price",
        type_=sa.Numeric(18, 4),
        existing_type=sa.Numeric(18, 6),
        nullable=False,
    )
    op.alter_column("transactions", "asset_id", existing_type=sa.Uuid(), nullable=False)

    # Yalnızca buy/sell satırları kaldığı varsayımıyla tip daraltılır.
    op.execute("ALTER TYPE transaction_type_enum RENAME TO transaction_type_enum_old")
    op.execute("CREATE TYPE transaction_type_enum AS ENUM ('buy','sell')")
    op.execute(
        "ALTER TABLE transactions ALTER COLUMN transaction_type "
        "TYPE transaction_type_enum USING transaction_type::text::transaction_type_enum"
    )
    op.execute("DROP TYPE transaction_type_enum_old")
