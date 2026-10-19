"""Add document indexing status.

Revision ID: c3a91e7b5d02
Revises: b7e2c9a41d08
Create Date: 2026-10-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a91e7b5d02"
down_revision: str | Sequence[str] | None = "b7e2c9a41d08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document", sa.Column("index_status", sa.String(length=32), nullable=True))
    op.add_column("document", sa.Column("index_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "index_error")
    op.drop_column("document", "index_status")
