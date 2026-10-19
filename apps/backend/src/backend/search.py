"""Retrieve a user's own chunks with hybrid search. This does not generate an answer."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.embeddings import EmbeddingClient, EmbeddingError
from backend.vector_store import SearchHit, VectorStore, VectorStoreError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    document_id: str
    chunk_index: int
    text: str
    headings: list[str]
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


@router.post("/search")
def search(body: SearchRequest, user: CurrentUser) -> SearchResponse:
    """Embed the query, fuse it with BM25, and return the caller's nearest chunks."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Enter a search query.")
    settings = get_settings()
    try:
        vector = EmbeddingClient.from_settings(settings).embed([query])[0]
        hits = VectorStore.from_settings(settings).hybrid_search(
            query=query,
            vector=vector,
            owner_user_id=user.id,
            top_k=body.top_k,
        )
    except (EmbeddingError, VectorStoreError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Search failed")
        raise HTTPException(status_code=503, detail="Search is unavailable.") from exc
    return SearchResponse(results=[_result(hit) for hit in hits])


def _result(hit: SearchHit) -> SearchResult:
    return SearchResult(
        document_id=hit.document_id,
        chunk_index=hit.chunk_index,
        text=hit.text,
        headings=hit.headings,
        score=hit.score,
    )
