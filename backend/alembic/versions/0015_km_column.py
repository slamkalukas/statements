"""Replace odometer_start/end with km on car_trips; add odometer_base on vehicles

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("car_trips", sa.Column("km", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE car_trips SET km = odometer_end - odometer_start "
        "WHERE odometer_start IS NOT NULL AND odometer_end IS NOT NULL"
    )
    op.drop_column("car_trips", "odometer_start")
    op.drop_column("car_trips", "odometer_end")
    op.add_column("vehicles", sa.Column("odometer_base", sa.Integer(), nullable=True))


def downgrade():
    op.add_column("car_trips", sa.Column("odometer_start", sa.Integer(), nullable=True))
    op.add_column("car_trips", sa.Column("odometer_end", sa.Integer(), nullable=True))
    op.drop_column("car_trips", "km")
    op.drop_column("vehicles", "odometer_base")
