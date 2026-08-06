"""service override cluster scope

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-06 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("service_overrides", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cluster_id", sa.Integer(), nullable=True))
        batch_op.alter_column("node_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key(
            "fk_service_overrides_cluster",
            "k8s_clusters",
            ["cluster_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_service_overrides_cluster", ["cluster_id", "container_name"]
        )


def downgrade() -> None:
    with op.batch_alter_table("service_overrides", schema=None) as batch_op:
        batch_op.drop_constraint("uq_service_overrides_cluster", type_="unique")
        batch_op.drop_constraint("fk_service_overrides_cluster", type_="foreignkey")
        batch_op.alter_column("node_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("cluster_id")
