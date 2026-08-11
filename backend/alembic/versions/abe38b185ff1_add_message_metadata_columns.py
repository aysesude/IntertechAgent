"""add message metadata columns

Revision ID: abe38b185ff1
Revises: 60bf3d7b4c54
Create Date: 2026-08-10 16:46:28.212301

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'abe38b185ff1'
down_revision: str | None = '60bf3d7b4c54'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# PostgreSQL'de ENUM tipi, kolon eklenmeden ÖNCE ayrıca oluşturulmalıdır.
# op.add_column(sa.Enum(...)) tipi kendiliğinden yaratmaz.
# create_type=False ile add_column'un tekrar yaratmaya çalışması engellenir.
message_status_enum = postgresql.ENUM(
    'complete', 'incomplete', name='message_status_enum', create_type=False
)


def upgrade() -> None:
    message_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('messages', sa.Column('agent_name', sa.String(length=64), nullable=True))
    op.add_column('messages', sa.Column('meta', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column(
        'messages',
        sa.Column('status', message_status_enum, server_default='complete', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('messages', 'status')
    op.drop_column('messages', 'meta')
    op.drop_column('messages', 'agent_name')

    message_status_enum.drop(op.get_bind(), checkfirst=True)
