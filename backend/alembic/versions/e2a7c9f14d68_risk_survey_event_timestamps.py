"""users: anket olayı zaman damgaları (Sinyal 5, Yol A)

Sinyal 5 (profil_sapmasi) yalnızca kullanıcının anketi YENİDEN DOLDURDUĞU
ANDA tetiklenmeli (bkz. agents/risk_agent.py modül docstring'i "2026-08-26" ve
"2026-08-28" ekleri, docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md).
`users.risk_survey_score` (f18c4a2e7b90) yalnızca kullanıcının MEVCUT puanını
tutuyor — anketin NE ZAMAN dolduğunu değil. "Mevcut puana bak" statik bir
durumdur, olay değildir; bu migration olayı yakalamak için gereken minimum
durumu ekliyor.

İki ayrı zaman damgası (tek bir boolean yerine): "ne zaman oldu" (anket ne
zaman güncellendi) ile "ne zaman görüldü" (bu güncelleme en son ne zaman bir
risk değerlendirmesine yansıtıldı) bilgisi ayrı ayrı taşınmalı — aksi hâlde
"bekleyen olay var mı" sorusu cevaplanamaz. "Bekleyen olay var" tanımı:
`risk_survey_updated_at IS NOT NULL AND (risk_survey_event_consumed_at IS
NULL OR risk_survey_event_consumed_at < risk_survey_updated_at)`.

İkisi de NULLABLE: mevcut satırlarda ne bir güncelleme anı ne de bir tüketim
anı uydurulabilir. `NULL` "bu kullanıcı için hiç anket-olayı yaşanmadı /
tüketilmedi" anlamına gelir ve `make seed` demo kullanıcılarına bir puan
atandığında bu iki alan boş kalır — seed verisinde bekleyen bir "olay"
simüle edilmiyor, bu bilinçli (yeni bir seed kullanıcısı için "az önce anketi
yeniden doldurdu" iddiası uydurma olurdu).

Revision ID: e2a7c9f14d68
Revises: ddaac4267bba
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2a7c9f14d68"
down_revision: str | None = "ddaac4267bba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("risk_survey_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("risk_survey_event_consumed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "risk_survey_event_consumed_at")
    op.drop_column("users", "risk_survey_updated_at")
