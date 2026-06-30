"""travel_legs: add leg_date for per-leg date on multi-day trips

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("travel_legs", sa.Column("leg_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("travel_legs", "leg_date")
