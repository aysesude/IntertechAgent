"""test ve risk-v3 migration uclarini birlestir

Revision ID: ddaac4267bba
Revises: a3d75e1c9f04, c7f4a1d9e6b2
Create Date: 2026-08-26 17:14:13.739943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ddaac4267bba'
down_revision: Union[str, None] = ('a3d75e1c9f04', 'c7f4a1d9e6b2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
