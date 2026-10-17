"""impact columns (filled by the background task) and a status/kind index

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("disruptions") as batch:
        batch.add_column(sa.Column("affected_connections", sa.Integer, nullable=True))
        batch.add_column(sa.Column("impact_score", sa.Float, nullable=True))
    op.create_index("ix_disruptions_status_kind", "disruptions", ["status", "kind"])


def downgrade() -> None:
    op.drop_index("ix_disruptions_status_kind", table_name="disruptions")
    with op.batch_alter_table("disruptions") as batch:
        batch.drop_column("impact_score")
        batch.drop_column("affected_connections")
