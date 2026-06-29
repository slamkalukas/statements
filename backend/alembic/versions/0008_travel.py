"""travel report (cestovné): trips per person per month

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "travels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("traveller_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("traveller_address", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("trip_date", sa.Date(), nullable=False),
        sa.Column("from_place", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("to_place", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("depart_time", sa.Time(), nullable=True),
        sa.Column("arrive_time", sa.Time(), nullable=True),
        sa.Column("return_depart_time", sa.Time(), nullable=True),
        sa.Column("return_arrive_time", sa.Time(), nullable=True),
        sa.Column("transport", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("per_diem_override", sa.Numeric(8, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_travels_period_id", "travels", ["period_id"])


def downgrade() -> None:
    op.drop_index("ix_travels_period_id", table_name="travels")
    op.drop_table("travels")
