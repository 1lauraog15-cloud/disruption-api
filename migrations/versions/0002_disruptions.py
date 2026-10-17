"""disruptions and recovery actions

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "disruptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("flight_id", sa.Integer, sa.ForeignKey("flights.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("delay_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("delay_minutes >= 0", name="ck_disruptions_delay_nonneg"),
    )
    op.create_table(
        "recovery_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("disruption_id", sa.Integer, sa.ForeignKey("disruptions.id"), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("recovery_actions")
    op.drop_table("disruptions")
