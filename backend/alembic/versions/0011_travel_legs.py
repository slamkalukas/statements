"""travel: legs sub-table — variable stops, per-leg transport / stravné / expense

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "travel_legs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("travel_id", sa.Integer(),
                  sa.ForeignKey("travels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("from_place", sa.String(120), nullable=False, server_default=""),
        sa.Column("to_place", sa.String(120), nullable=False, server_default=""),
        sa.Column("transport", sa.String(60), nullable=False, server_default=""),
        sa.Column("leg_time", sa.Time(), nullable=True),
        sa.Column("distance_km", sa.Numeric(8, 2), nullable=True),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        sa.Column("expense", sa.Numeric(10, 2), nullable=True),
        sa.Column("per_diem", sa.Numeric(8, 2), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_travel_legs_travel_id", "travel_legs", ["travel_id"])

    # Migrate existing single-leg travel data
    op.execute("""
        INSERT INTO travel_legs
            (travel_id, order_idx, from_place, to_place, transport,
             distance_km, duration_min, per_diem)
        SELECT id, 0,
               COALESCE(from_place, ''), COALESCE(to_place, ''),
               COALESCE(transport, ''),
               distance_km, duration_min, per_diem_override
        FROM travels
        WHERE COALESCE(from_place, '') != '' OR COALESCE(to_place, '') != ''
    """)

    op.drop_column("travels", "from_place")
    op.drop_column("travels", "to_place")
    op.drop_column("travels", "transport")
    op.drop_column("travels", "per_diem_override")
    op.drop_column("travels", "distance_km")
    op.drop_column("travels", "duration_min")


def downgrade() -> None:
    op.add_column("travels", sa.Column("from_place", sa.String(120), nullable=True))
    op.add_column("travels", sa.Column("to_place", sa.String(120), nullable=True))
    op.add_column("travels", sa.Column("transport", sa.String(60), nullable=True))
    op.add_column("travels", sa.Column("per_diem_override", sa.Numeric(8, 2), nullable=True))
    op.add_column("travels", sa.Column("distance_km", sa.Numeric(8, 2), nullable=True))
    op.add_column("travels", sa.Column("duration_min", sa.Integer(), nullable=True))
    op.drop_index("ix_travel_legs_travel_id", table_name="travel_legs")
    op.drop_table("travel_legs")
