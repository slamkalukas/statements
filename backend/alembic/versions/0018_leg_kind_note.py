"""travel_legs: add kind (travel|stay) and note

A "stay" leg records a day spent in one place without travelling — a
conference, training, multi-day negotiation — and `note` says what it was.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "travel_legs",
        sa.Column("kind", sa.String(20), nullable=False, server_default="travel"),
    )
    op.add_column(
        "travel_legs",
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_column("travel_legs", "note")
    op.drop_column("travel_legs", "kind")
