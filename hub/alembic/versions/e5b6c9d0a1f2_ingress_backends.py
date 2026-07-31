"""ingress backends

Revision ID: e5b6c9d0a1f2
Revises: d8e3f0a2b6c7
Create Date: 2026-08-01 00:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e5b6c9d0a1f2'
down_revision: str | None = 'd8e3f0a2b6c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('k8s_ingresses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('backends_json', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('k8s_ingresses', schema=None) as batch_op:
        batch_op.drop_column('backends_json')
