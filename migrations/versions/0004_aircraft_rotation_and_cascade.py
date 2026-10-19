"""aircraft rotation (tail number, arrival time) and knock-on disruptions (parent_id)

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("flights") as batch:
        batch.add_column(sa.Column("tail_number", sa.String(10), nullable=True))
        batch.add_column(sa.Column("scheduled_arrival", sa.DateTime, nullable=True))
        batch.create_check_constraint(
            "ck_flights_arrival_after_departure",
            "scheduled_arrival IS NULL OR scheduled_arrival > scheduled_departure",
        )
    op.create_index("ix_flights_tail_number", "flights", ["tail_number"])
    with op.batch_alter_table("disruptions") as batch:
        batch.add_column(sa.Column("parent_id", sa.Integer, nullable=True))
        batch.create_foreign_key("fk_disruptions_parent_id", "disruptions", ["parent_id"], ["id"])
    op.create_index("ix_disruptions_parent_id", "disruptions", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_disruptions_parent_id", table_name="disruptions")
    with op.batch_alter_table("disruptions") as batch:
        batch.drop_constraint("fk_disruptions_parent_id", type_="foreignkey")
        batch.drop_column("parent_id")
    op.drop_index("ix_flights_tail_number", table_name="flights")
    with op.batch_alter_table("flights") as batch:
        batch.drop_constraint("ck_flights_arrival_after_departure", type_="check")
        batch.drop_column("scheduled_arrival")
        batch.drop_column("tail_number")
