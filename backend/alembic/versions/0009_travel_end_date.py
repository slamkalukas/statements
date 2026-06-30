"""multi-day trips: travel end date

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("travels", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("travels", "end_date")
