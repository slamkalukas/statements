"""tag statement lines with their source account (e.g. bank vs credit card)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "statement_lines",
        sa.Column(
            "source",
            sa.String(length=60),
            nullable=False,
            server_default="Bank account",
        ),
    )


def downgrade() -> None:
    op.drop_column("statement_lines", "source")
