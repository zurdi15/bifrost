"""container network mode

Revision ID: b7c8d9e0f1a2
Revises: f3c4d5e6a7b8
Create Date: 2026-08-03 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b7c8d9e0f1a2'
down_revision: str | None = 'b5c6d7e8f9a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('containers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('network_mode', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('containers', schema=None) as batch_op:
        batch_op.drop_column('network_mode')
