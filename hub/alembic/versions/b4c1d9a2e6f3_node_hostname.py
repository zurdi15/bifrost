"""node hostname

Revision ID: b4c1d9a2e6f3
Revises: 6e3d1c5a7c1b
Create Date: 2026-07-31 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b4c1d9a2e6f3'
down_revision: str | None = '6e3d1c5a7c1b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('nodes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hostname', sa.String(), nullable=True))
    # Existing names came straight from the agent's hello, so seeding
    # hostname=name lets the hub keep following the reported hostname until
    # the user renames the node explicitly.
    op.execute("UPDATE nodes SET hostname = name WHERE kind = 'agent'")


def downgrade() -> None:
    with op.batch_alter_table('nodes', schema=None) as batch_op:
        batch_op.drop_column('hostname')
