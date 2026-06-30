"""travel: per-leg depart/arrive times; remove trip-level time columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Replace single leg_time with depart + arrive on each leg
    op.drop_column("travel_legs", "leg_time")
    op.add_column("travel_legs", sa.Column("depart_time", sa.Time(), nullable=True))
    op.add_column("travel_legs", sa.Column("arrive_time", sa.Time(), nullable=True))

    # Migrate: first (and only) leg of each existing trip gets the trip-level times
    op.execute("""
        UPDATE travel_legs tl
        SET depart_time = t.depart_time,
            arrive_time = t.arrive_time
        FROM travels t
        WHERE tl.travel_id = t.id
          AND tl.order_idx = (
              SELECT MIN(order_idx) FROM travel_legs WHERE travel_id = t.id
          )
    """)

    # Drop the four trip-level time columns (now redundant)
    op.drop_column("travels", "depart_time")
    op.drop_column("travels", "arrive_time")
    op.drop_column("travels", "return_depart_time")
    op.drop_column("travels", "return_arrive_time")


def downgrade() -> None:
    op.add_column("travels", sa.Column("depart_time", sa.Time(), nullable=True))
    op.add_column("travels", sa.Column("arrive_time", sa.Time(), nullable=True))
    op.add_column("travels", sa.Column("return_depart_time", sa.Time(), nullable=True))
    op.add_column("travels", sa.Column("return_arrive_time", sa.Time(), nullable=True))
    op.drop_column("travel_legs", "arrive_time")
    op.drop_column("travel_legs", "depart_time")
    op.add_column("travel_legs", sa.Column("leg_time", sa.Time(), nullable=True))
