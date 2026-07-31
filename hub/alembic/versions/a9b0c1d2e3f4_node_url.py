"""node url

Revision ID: a9b0c1d2e3f4
Revises: f3c4d5e6a7b8
Create Date: 2026-08-01 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a9b0c1d2e3f4'
down_revision: str | None = 'f3c4d5e6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('nodes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('url', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('nodes', schema=None) as batch_op:
        batch_op.drop_column('url')
