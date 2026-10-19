"""Application tables. Better Auth tables live outside this metadata."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    """A file converted to Markdown for one signed-in user.

    `markdown` holds the conversion result. `index_status` tracks the later
    chunk-and-embed step. The vectors themselves live in Qdrant.
    """

    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(127))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    index_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
