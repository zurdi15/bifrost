"""service overrides

Revision ID: c7d2e8f1a4b5
Revises: b4c1d9a2e6f3
Create Date: 2026-07-31 20:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c7d2e8f1a4b5'
down_revision: str | None = 'b4c1d9a2e6f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'service_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('node_id', sa.Integer(), nullable=False),
        sa.Column('container_name', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('group_name', sa.String(), nullable=True),
        sa.Column('hide', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['node_id'], ['nodes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('node_id', 'container_name'),
    )


def downgrade() -> None:
    op.drop_table('service_overrides')
