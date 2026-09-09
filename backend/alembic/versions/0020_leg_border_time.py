"""travel_legs: add border_time (prechod štátnej hranice)

The moment a leg crossed the state border, which is what splits domestic
from foreign stravné for that day. Only recorded for overland travel; blank
means the calculation falls back to the leg's arrival, as before.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("travel_legs", sa.Column("border_time", sa.Time(), nullable=True))


def downgrade():
    op.drop_column("travel_legs", "border_time")
