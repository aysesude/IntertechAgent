"""assets.tradable ve anket zaman damgalari uclarini birlestir

BOS MIGRATION, BILEREK: sema degistirmiyor, yalnizca zinciri tek uca indiriyor.

Iki migration ayni ebeveyni (`ddaac4267bba`) gosteriyordu:

  ddaac4267bba
    |- e8e6807ad5c4 (hedef fiyatlar) -> e4c17a8b3d90 (assets.tradable)
    `- e2a7c9f14d68 (anket zaman damgalari)

`alembic upgrade head` iki uc varken calismaz ("Multiple head revisions are
present"), yani deploy'un goc adimi duser ve SEMA OLDUGU YERDE KALIR. Kod ise
yeni surumle acilir: `models/user.py` DB'de olmayan `risk_survey_updated_at` /
`risk_survey_event_consumed_at` kolonlarini secmeye calisir ve `users`
tablosuna dokunan HER sorgu patlar. Sahadaki karsiligi, 29 Agustos 2026'da
test ortaminda girisin 500 dondurmesiydi: kimse giris yapamiyordu.

Ucu birlestirmek, birinin migration'ini digerinin ustune ZINCIRLEMEKTEN
guvenli: iki migration da baska ortamlarda tek tek uygulanmis olabilir ve
gecmisi yeniden yazmak o ortamlarin `alembic_version` kaydini gecersiz kilar.

Revision ID: d348eb272d1c
Revises: e2a7c9f14d68, e4c17a8b3d90
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd348eb272d1c'
down_revision: Union[str, None] = ('e2a7c9f14d68', 'e4c17a8b3d90')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
