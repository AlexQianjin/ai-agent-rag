"""Authenticated document upload, conversion, and lookup."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.conversion import DocumentRejected, convert_to_markdown, validate_upload
from backend.db import SessionLocal, get_db
from backend.indexing import schedule_indexing
from backend.models import Document

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

DbSession = Annotated[Session, Depends(get_db)]


class DocumentSummary(BaseModel):
    id: str
    filename: str
    mime_type: str
    status: str
    index_status: str | None
    error_message: str | None
    index_error: str | None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    markdown: str | None


class DocumentList(BaseModel):
    documents: list[DocumentSummary]


def _summary(document: Document) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        filename=document.filename,
        mime_type=document.mime_type,
        status=document.status,
        index_status=document.index_status,
        error_message=document.error_message,
        index_error=document.index_error,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _owned(db: Session, document_id: str, user_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def run_conversion(document_id: str, source_path: str) -> None:
    """Convert one stored upload and record the Markdown.

    Runs outside the request session. On success it calls `schedule_indexing`,
    which chunks the Markdown and writes vectors to Qdrant.
    """
    path = Path(source_path)
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.status = "processing"
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
        try:
            markdown = convert_to_markdown(path, document.filename)
        except DocumentRejected as exc:
            _mark_failed(document, exc.message)
            db.commit()
            return
        except Exception:
            logger.exception("Document conversion failed for %s", document_id)
            _mark_failed(document, "Conversion failed.")
            db.commit()
            return
        document.markdown = markdown
        document.status = "ready"
        document.index_status = "pending"
        document.error_message = None
        document.index_error = None
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
        schedule_indexing(document.id)
    finally:
        db.close()
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass


def _mark_failed(document: Document, message: str) -> None:
    document.status = "failed"
    document.error_message = message
    document.updated_at = datetime.now(timezone.utc)


@router.get("/documents")
def list_documents(user: CurrentUser, db: DbSession) -> DocumentList:
    """List the signed-in user's documents, newest first."""
    rows = db.scalars(
        select(Document).where(Document.owner_user_id == user.id).order_by(Document.created_at.desc())
    ).all()
    return DocumentList(documents=[_summary(row) for row in rows])


@router.get("/documents/{document_id}")
def get_document(document_id: str, user: CurrentUser, db: DbSession) -> DocumentDetail:
    """Return one document, including Markdown when conversion has finished."""
    document = _owned(db, document_id, user.id)
    return DocumentDetail(**_summary(document).model_dump(), markdown=document.markdown)


@router.post("/documents", status_code=201)
async def create_document(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
) -> DocumentSummary:
    """Accept a file, store a pending row, and convert it in the background."""
    settings = get_settings()
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="The file needs a name.")
    payload = await file.read(settings.max_upload_bytes + 1)
    try:
        mime_type = validate_upload(filename, len(payload), limit=settings.max_upload_bytes)
    except DocumentRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    document = Document(
        id=str(uuid4()),
        owner_user_id=user.id,
        filename=filename,
        mime_type=mime_type,
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    upload_dir = Path(tempfile.mkdtemp(prefix="doc-"))
    source_path = upload_dir / f"{document.id}{Path(filename).suffix.lower()}"
    source_path.write_bytes(payload)
    background_tasks.add_task(run_conversion, document.id, str(source_path))
    return _summary(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, user: CurrentUser, db: DbSession) -> None:
    """Delete one document and its vectors."""
    document = _owned(db, document_id, user.id)
    try:
        from backend.vector_store import VectorStore, VectorStoreError

        VectorStore.from_settings(get_settings()).delete_document(document.id)
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not delete vectors for %s", document_id)
        raise HTTPException(status_code=503, detail="Could not delete the document index.") from exc
    db.delete(document)
    db.commit()
