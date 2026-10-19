"""Authenticated conversations and a streaming chat turn."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agent import AgentError, stream_turn
from backend.auth import CurrentUser
from backend.db import get_db
from backend.documents import DocumentSummary
from backend.embeddings import EmbeddingError
from backend.models import Conversation, Document, Message
from backend.vector_store import VectorStoreError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])

DbSession = Annotated[Session, Depends(get_db)]
DEFAULT_TITLE = "New conversation"


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class CitationOut(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int
    text: str
    headings: list[str]
    score: float


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[CitationOut]
    created_at: datetime


class ConversationList(BaseModel):
    conversations: list[ConversationSummary]


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]
    documents: list[DocumentSummary]


def _summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message(message: Message) -> MessageOut:
    citations = []
    for item in message.citations or []:
        if isinstance(item, dict):
            citations.append(CitationOut.model_validate(item))
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=citations,
        created_at=message.created_at,
    )


def _owned(db: Session, conversation_id: str, user_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _detail(db: Session, conversation: Conversation) -> ConversationDetail:
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at, Message.id)
    ).all()
    documents = db.scalars(
        select(Document)
        .where(Document.conversation_id == conversation.id, Document.owner_user_id == conversation.owner_user_id)
        .order_by(Document.created_at.desc())
    ).all()
    return ConversationDetail(
        **_summary(conversation).model_dump(),
        messages=[_message(message) for message in messages],
        documents=[DocumentSummary.model_validate(document, from_attributes=True) for document in documents],
    )


@router.get("/conversations")
def list_conversations(user: CurrentUser, db: DbSession) -> ConversationList:
    """List the signed-in user's conversations, most recently updated first."""
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.owner_user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return ConversationList(conversations=[_summary(row) for row in rows])


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationCreate, user: CurrentUser, db: DbSession) -> ConversationSummary:
    """Start a conversation. The title can be filled in later from the first message."""
    title = (body.title or "").strip() or DEFAULT_TITLE
    now = datetime.now(timezone.utc)
    conversation = Conversation(
        id=str(uuid4()),
        owner_user_id=user.id,
        title=title[:200],
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _summary(conversation)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> ConversationDetail:
    """Return one conversation, its messages, and files uploaded from it."""
    return _detail(db, _owned(db, conversation_id, user.id))


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ConversationSummary:
    """Rename a conversation the caller owns."""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Enter a title.")
    conversation = _owned(db, conversation_id, user.id)
    conversation.title = title[:200]
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conversation)
    return _summary(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> None:
    """Delete a conversation and its messages. Uploaded documents stay in the library."""
    conversation = _owned(db, conversation_id, user.id)
    db.delete(conversation)
    db.commit()


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: str,
    body: MessageCreate,
    user: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    """Stream one agent turn, then store the user and assistant messages."""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Enter a message.")
    conversation = _owned(db, conversation_id, user.id)
    history = [
        {"role": message.role, "content": message.content}
        for message in db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at, Message.id)
        ).all()
    ][-20:]
    now = datetime.now(timezone.utc)
    user_message = Message(
        id=str(uuid4()),
        conversation_id=conversation.id,
        role="user",
        content=content,
        citations=[],
        created_at=now,
    )
    db.add(user_message)
    if conversation.title == DEFAULT_TITLE:
        conversation.title = content.replace("\n", " ").strip()[:80] or DEFAULT_TITLE
    conversation.updated_at = now
    db.commit()
    owner_id = user.id
    conversation_key = conversation.id

    def events() -> Iterator[str]:
        sources: list[dict] = []
        parts: list[str] = []
        try:
            for event in stream_turn(user_id=owner_id, query=content, history=history):
                kind = str(event.get("type") or "status")
                if kind == "retrieved":
                    sources = list(event.get("sources") or [])
                elif kind == "token":
                    parts.append(str(event.get("delta") or ""))
                yield _sse(kind, {key: value for key, value in event.items() if key != "type"})
            answer = "".join(parts)
            saved = _save_assistant(conversation_key, answer, sources, now)
            yield _sse(
                "done",
                {"message_id": saved, "content": answer, "citations": sources},
            )
        except (AgentError, EmbeddingError, VectorStoreError) as exc:
            logger.warning("Chat turn failed: %s", exc)
            _save_partial(conversation_key, parts, sources, now)
            yield _sse("error", {"message": str(exc)})
        except Exception:
            logger.exception("Chat turn failed")
            _save_partial(conversation_key, parts, sources, now)
            yield _sse("error", {"message": "The assistant is unavailable."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _save_assistant(conversation_id: str, content: str, citations: list[dict], user_created: datetime) -> str:
    from backend.db import SessionLocal

    db = SessionLocal()
    try:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            return ""
        created = datetime.now(timezone.utc)
        if created <= user_created:
            created = user_created + timedelta(microseconds=1)
        message = Message(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            citations=citations,
            created_at=created,
        )
        conversation.updated_at = created
        db.add(message)
        db.commit()
        return message.id
    finally:
        db.close()


def _save_partial(conversation_id: str, parts: list[str], citations: list[dict], user_created: datetime) -> None:
    if not parts:
        return
    try:
        _save_assistant(conversation_id, "".join(parts), citations, user_created)
    except Exception:
        logger.exception("Could not save a partial answer")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
