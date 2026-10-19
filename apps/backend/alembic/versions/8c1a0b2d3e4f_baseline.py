"""Baseline schema. No application tables yet.

Revision ID: 8c1a0b2d3e4f
Revises:
Create Date: 2026-10-19

"""

from collections.abc import Sequence

revision: str = "8c1a0b2d3e4f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
