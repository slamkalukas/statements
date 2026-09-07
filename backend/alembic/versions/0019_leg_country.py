"""travel_legs: add country for foreign per-diem (zahraničné stravné)

The country a leg arrives in. Empty means home, and a trip is treated as
foreign once any of its legs has one — putting it on the leg rather than the
trip is what allows a single trip to span several countries.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "travel_legs",
        sa.Column("country", sa.String(8), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_column("travel_legs", "country")
