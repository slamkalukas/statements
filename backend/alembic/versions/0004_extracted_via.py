"""track how a document's amount/date were read (text layer vs OCR)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("extracted_via", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "extracted_via")
