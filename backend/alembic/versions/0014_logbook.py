"""Logbook: vehicles and car_trips tables

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ecv", sa.String(20), nullable=False),
        sa.Column("vin", sa.String(20), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(60), nullable=False, server_default=""),
        sa.Column("car_model", sa.String(60), nullable=False, server_default=""),
        sa.Column("fuel_type", sa.String(30), nullable=False, server_default=""),
        sa.Column("consumption", sa.Numeric(6, 2), nullable=True),
        sa.Column("fuel_price", sa.Numeric(8, 4), nullable=True),
        sa.Column("ownership", sa.String(30), nullable=False, server_default="Firemné"),
        sa.Column("date_added", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecv", name="uq_vehicle_ecv"),
    )
    op.create_table(
        "car_trips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(),
                  sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("journey_number", sa.Integer(), nullable=False),
        sa.Column("start_dt", sa.DateTime(), nullable=False),
        sa.Column("end_dt", sa.DateTime(), nullable=True),
        sa.Column("purpose", sa.String(255), nullable=False, server_default=""),
        sa.Column("route", sa.String(1000), nullable=False, server_default=""),
        sa.Column("odometer_start", sa.Integer(), nullable=True),
        sa.Column("odometer_end", sa.Integer(), nullable=True),
        sa.Column("driver_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("trip_type", sa.String(30), nullable=False, server_default="Firemná"),
        sa.Column("events", sa.String(255), nullable=True),
        sa.Column("fuel_price_override", sa.Numeric(8, 4), nullable=True),
        sa.Column("travel_id", sa.Integer(),
                  sa.ForeignKey("travels.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("car_trips")
    op.drop_table("vehicles")
