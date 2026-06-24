"""add statement_lines for reconciliation

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "statement_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("payee", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_statement_lines_period_id", "statement_lines", ["period_id"])
    op.create_index("ix_statement_lines_document_id", "statement_lines", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_statement_lines_document_id", table_name="statement_lines")
    op.drop_index("ix_statement_lines_period_id", table_name="statement_lines")
    op.drop_table("statement_lines")
