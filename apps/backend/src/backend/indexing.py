"""Chunk a ready document, embed it, and upsert the vectors.

`schedule_indexing` is the seam the conversion task already calls. It records
`indexing`, then `indexed` or `failed`, on the document row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select

from backend.chunking import chunk_markdown
from backend.config import get_settings
from backend.db import SessionLocal
from backend.embeddings import EmbeddingError
from backend.models import Document
from backend.vector_store import VectorStoreError

# Dense-only points from the earlier index are version 1, implicitly.
# Version 2 stores a BM25 sparse vector beside the dense vector.
HYBRID_INDEX_VERSION = 2

logger = logging.getLogger(__name__)


def schedule_indexing(document_id: str) -> None:
    """Index one document. Failures stay on the row and do not propagate."""
    try:
        index_document(document_id)
    except Exception:
        logger.exception("Indexing failed for %s", document_id)
        _mark_index_failed(document_id, "Indexing failed.")


def index_document(document_id: str) -> None:
    """Load Markdown, embed its chunks, and replace that document's vectors."""
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        markdown = (document.markdown or "").strip()
        if not markdown:
            document.index_status = "failed"
            document.index_error = "Nothing to index."
            document.updated_at = datetime.now(timezone.utc)
            db.commit()
            return
        owner_user_id = document.owner_user_id
        document.index_status = "indexing"
        document.index_error = None
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    try:
        chunks = chunk_markdown(markdown)
        if not chunks:
            raise VectorStoreError("Nothing to index.")
        from backend.embeddings import EmbeddingClient

        settings = get_settings()
        vectors = EmbeddingClient.from_settings(settings).embed([chunk.text for chunk in chunks])
        from backend.vector_store import VectorStore

        VectorStore.from_settings(settings).replace_document(
            document_id=document_id,
            owner_user_id=owner_user_id,
            chunks=chunks,
            vectors=vectors,
        )
    except (EmbeddingError, VectorStoreError) as exc:
        _mark_index_failed(document_id, str(exc))
        return
    except Exception:
        logger.exception("Indexing failed for %s", document_id)
        _mark_index_failed(document_id, "Indexing failed.")
        return
    _mark_indexed(document_id)


def _mark_indexed(document_id: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.index_status = "indexed"
        document.index_error = None
        document.index_version = HYBRID_INDEX_VERSION
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _mark_index_failed(document_id: str, message: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.index_status = "failed"
        document.index_error = message
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def backfill_hybrid_index(*, force: bool = False) -> None:
    """Reindex documents whose vectors predate BM25.

    Qdrant 1.15 cannot add a sparse vector in place, so a dense-only collection
    is replaced first. Documents already stored at the hybrid version are left
    alone unless that replacement dropped their points.
    """
    settings = get_settings()
    if not force and not settings.hybrid_backfill:
        return
    from backend.vector_store import VectorStore

    try:
        rebuilt = VectorStore.from_settings(settings).migrate_to_hybrid()
    except Exception:
        logger.exception("Could not prepare the hybrid collection")
        return
    db = SessionLocal()
    try:
        query = select(Document).where(Document.status == "ready", Document.markdown.is_not(None))
        if not rebuilt:
            query = query.where(
                or_(Document.index_version.is_(None), Document.index_version < HYBRID_INDEX_VERSION)
            )
        ids = [row.id for row in db.scalars(query).all()]
    finally:
        db.close()
    if ids:
        logger.info("Reindexing %s document(s) for hybrid search", len(ids))
    for document_id in ids:
        index_document(document_id)
