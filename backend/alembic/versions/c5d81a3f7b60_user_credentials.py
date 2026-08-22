"""users: kimlik doğrulama sütunları (national_id, password_hash, last_login_at)

FR-0 / AK 5.4. Şimdiye kadar sistemde oturum kavramı yoktu; kullanıcı
arayüzden doğrudan UUID vererek herhangi bir portföyü okuyabiliyordu.

ÜÇÜ DE NULLABLE, bilerek:
- Bu sütunlar mevcut satırların üzerine ekleniyor ve bir migration içinde
  bcrypt özeti üretilemez (özet uygulama kodunun işi, SQL'in değil).
- `NULL` anlamlı bir durumdur ve öyle kalacaktır: "bu kullanıcıya kimlik
  bilgisi atanmamış, giriş yapamaz." `auth_service` NULL özetli satırı hiçbir
  şifreyle eşleştirmez.
- Demo kullanıcılarının tamamını `make seed` doldurur.

`national_id` (T.C. kimlik numarası) String(11): baştaki sıfır korunmalı ve
üzerinde aritmetik yapılmıyor. UNIQUE, çünkü giriş sorgusu tek satır bulmak
zorunda. Kısmi (partial) indeks kullanılmadı: Postgres'te de SQLite'ta da
UNIQUE kısıtı birden fazla NULL'a izin verir, dolayısıyla kimlik bilgisi
atanmamış 50 satır sorun çıkarmaz.

Revision ID: c5d81a3f7b60
Revises: b26e8dab6ef9
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d81a3f7b60"
down_revision: str | None = "b26e8dab6ef9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("national_id", sa.String(length=11), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    # İsim açıkça veriliyor: downgrade'in ve ileride olası bir değişikliğin
    # veritabanının ürettiği rastgele isme bağlı kalmaması için.
    op.create_unique_constraint("uq_users_national_id", "users", ["national_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_national_id", "users", type_="unique")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "national_id")
