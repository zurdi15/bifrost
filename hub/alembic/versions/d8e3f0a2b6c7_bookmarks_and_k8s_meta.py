"""bookmarks and k8s workload meta

Revision ID: d8e3f0a2b6c7
Revises: c7d2e8f1a4b5
Create Date: 2026-07-31 23:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd8e3f0a2b6c7'
down_revision: str | None = 'c7d2e8f1a4b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'bookmarks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('group_name', sa.String(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('k8s_workloads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('meta_json', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('k8s_workloads', schema=None) as batch_op:
        batch_op.drop_column('meta_json')
    op.drop_table('bookmarks')
