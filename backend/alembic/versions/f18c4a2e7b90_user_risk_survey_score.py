"""users: anket risk puanı (risk_survey_score, 1-7)

Şartname: "Kullanıcıların çözdüğü anket sonucu 1-7 arası bir risk puanı olur."
Bugüne kadar sistemde o puanın yaşayacağı bir yer yoktu; `users.risk_profile`
dört kademeliydi ve uygunluk kontrolü (`advice_eligibility`) yedi kademelik
bir puan bekliyordu. Aradaki boşluk `agents/risk_agent.py` içinde GEÇİCİ bir
profil→puan eşlemesiyle doldurulmuştu. Bu migration puanın kendisine kalıcı
bir yer açıyor.

NULLABLE, bilerek. Mevcut satırlara bir anket sonucu uydurulamaz — kullanıcı
o anketi doldurmadı. `NULL` anlamlıdır ve öyle kalacaktır: "bu kullanıcının
kayıtlı bir anket sonucu yok." Okuyan taraf bu durumda `risk_profile`'a
düşer. `make seed` demo kullanıcılarının tamamını doldurur.

CHECK kısıtı 1-7 aralığını VERİTABANI düzeyinde kilitler. Doğrulama zaten
Pydantic'te ve `advice_eligibility.validate_survey_score` içinde var; buradaki
üçüncü kopya, uygulamayı atlayan bir yol (elle SQL, veri aktarımı, ileride
yazılacak bir betik) aralık dışı bir puan yazarsa uygunluk kontrolünün
sessizce hak edilmemiş genişlikte tavsiye üretmesini engelliyor.

Revision ID: f18c4a2e7b90
Revises: c5d81a3f7b60
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f18c4a2e7b90"
down_revision: str | None = "c5d81a3f7b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_NAME = "ck_users_risk_survey_score_range"


def upgrade() -> None:
    op.add_column("users", sa.Column("risk_survey_score", sa.Integer(), nullable=True))
    # İsim açıkça veriliyor: downgrade'in veritabanının ürettiği rastgele
    # isme bağlı kalmaması için (c5d81a3f7b60'daki UNIQUE ile aynı gerekçe).
    op.create_check_constraint(
        _CHECK_NAME,
        "users",
        "risk_survey_score IS NULL OR (risk_survey_score BETWEEN 1 AND 7)",
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "users", type_="check")
    op.drop_column("users", "risk_survey_score")
