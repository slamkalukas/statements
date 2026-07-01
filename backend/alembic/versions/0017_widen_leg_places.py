"""Widen travel_legs.from_place/to_place to fit full street/POI addresses

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("travel_legs", "from_place", type_=sa.String(255), existing_nullable=False)
    op.alter_column("travel_legs", "to_place", type_=sa.String(255), existing_nullable=False)


def downgrade():
    op.alter_column("travel_legs", "from_place", type_=sa.String(120), existing_nullable=False)
    op.alter_column("travel_legs", "to_place", type_=sa.String(120), existing_nullable=False)
