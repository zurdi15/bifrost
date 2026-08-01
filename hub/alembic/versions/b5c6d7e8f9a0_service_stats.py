"""service stats

Revision ID: b5c6d7e8f9a0
Revises: a9b0c1d2e3f4
Create Date: 2026-08-01 03:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b5c6d7e8f9a0'
down_revision: str | None = 'a9b0c1d2e3f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('containers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpu_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('mem_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('mem_bytes', sa.Integer(), nullable=True))
    with op.batch_alter_table('k8s_workloads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpu_millis', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('mem_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('k8s_workloads', schema=None) as batch_op:
        batch_op.drop_column('mem_bytes')
        batch_op.drop_column('cpu_millis')
    with op.batch_alter_table('containers', schema=None) as batch_op:
        batch_op.drop_column('mem_bytes')
        batch_op.drop_column('mem_pct')
        batch_op.drop_column('cpu_pct')
