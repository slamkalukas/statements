"""travel: store routed distance and duration

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One-way km (round-trip shown in UI as 2×); NULL = not yet calculated.
    op.add_column("travels", sa.Column("distance_km", sa.Numeric(8, 2), nullable=True))
    # One-way travel time in minutes, rounded to nearest 20; NULL = not calculated.
    op.add_column("travels", sa.Column("duration_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("travels", "duration_min")
    op.drop_column("travels", "distance_km")
