"""period_tasks: recurring monthly to-dos, plus a wider settings.value

Each month gets its own copy of the task titles kept in settings, so editing
the template later leaves months already filed untouched. settings.value grows
to Text because the template (and the foreign per-diem table before it) is JSON
that outgrows 512 characters once there are a dozen entries.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "period_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["period_id"], ["periods.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_period_tasks_period_id", "period_tasks", ["period_id"])
    op.alter_column("settings", "value", type_=sa.Text(), existing_nullable=False)


def downgrade():
    op.alter_column("settings", "value", type_=sa.String(length=512), existing_nullable=False)
    op.drop_index("ix_period_tasks_period_id", table_name="period_tasks")
    op.drop_table("period_tasks")
