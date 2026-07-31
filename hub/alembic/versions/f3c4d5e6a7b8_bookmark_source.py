"""bookmark source

Revision ID: f3c4d5e6a7b8
Revises: e5b6c9d0a1f2
Create Date: 2026-08-01 01:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'f3c4d5e6a7b8'
down_revision: str | None = 'e5b6c9d0a1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('bookmarks', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('source', sa.String(), nullable=False, server_default='ui')
        )


def downgrade() -> None:
    with op.batch_alter_table('bookmarks', schema=None) as batch_op:
        batch_op.drop_column('source')
