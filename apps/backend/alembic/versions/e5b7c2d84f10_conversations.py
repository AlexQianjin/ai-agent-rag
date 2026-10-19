"""Add conversations, messages, and document link columns.

Revision ID: e5b7c2d84f10
Revises: c3a91e7b5d02
Create Date: 2026-10-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b7c2d84f10"
down_revision: str | Sequence[str] | None = "c3a91e7b5d02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversation_owner_user_id", "conversation", ["owner_user_id"])
    op.create_table(
        "message",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])
    op.add_column("document", sa.Column("conversation_id", sa.String(length=36), nullable=True))
    op.add_column("document", sa.Column("index_version", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_document_conversation_id",
        "document",
        "conversation",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_document_conversation_id", "document", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_document_conversation_id", table_name="document")
    op.drop_constraint("fk_document_conversation_id", "document", type_="foreignkey")
    op.drop_column("document", "index_version")
    op.drop_column("document", "conversation_id")
    op.drop_index("ix_message_conversation_id", table_name="message")
    op.drop_table("message")
    op.drop_index("ix_conversation_owner_user_id", table_name="conversation")
    op.drop_table("conversation")
