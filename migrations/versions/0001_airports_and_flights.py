"""airports and flights

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "airports",
        sa.Column("iata", sa.String(3), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_hub", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "flights",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(8), nullable=False),
        sa.Column("origin", sa.String(3), sa.ForeignKey("airports.iata"), nullable=False),
        sa.Column("destination", sa.String(3), sa.ForeignKey("airports.iata"), nullable=False),
        sa.Column("scheduled_departure", sa.DateTime, nullable=False),
        sa.Column("passengers", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("passengers >= 0", name="ck_flights_passengers_nonneg"),
        sa.CheckConstraint("origin <> destination", name="ck_flights_origin_ne_dest"),
    )
    op.create_index("ix_flights_number", "flights", ["number"])


def downgrade() -> None:
    op.drop_index("ix_flights_number", table_name="flights")
    op.drop_table("flights")
    op.drop_table("airports")
