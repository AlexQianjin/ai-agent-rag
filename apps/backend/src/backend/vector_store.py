"""Qdrant collection for document chunks.

The collection uses cosine distance and 1024-dimensional vectors, matching
BGE-M3. It is created on first use when it is missing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from backend.chunking import TextChunk
from backend.config import Settings

_NAMESPACE = uuid.UUID("8f3b1c2a-6d4e-5f70-9a1b-2c3d4e5f6071")


class VectorStoreError(Exception):
    """Qdrant could not store or read vectors."""


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    chunk_index: int
    text: str
    headings: list[str]
    score: float


class VectorStore:
    def __init__(self, *, url: str, collection: str, dimension: int, timeout: float = 30) -> None:
        self.collection = collection
        self.dimension = dimension
        self.client = QdrantClient(url=url, timeout=timeout, prefer_grpc=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> VectorStore:
        return cls(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dimension=settings.embedding_dimension,
        )

    def ensure_collection(self) -> None:
        exists = self.client.collection_exists(self.collection)
        if not exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="owner_user_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="document_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            return
        info = self.client.get_collection(self.collection)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        if size != self.dimension:
            raise VectorStoreError(
                f"Collection {self.collection} has dimension {size}, expected {self.dimension}."
            )

    def replace_document(
        self,
        *,
        document_id: str,
        owner_user_id: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreError("Each chunk needs one vector.")
        self.ensure_collection()
        self.delete_document(document_id)
        if not chunks:
            return
        points = [
            PointStruct(
                id=str(uuid.uuid5(_NAMESPACE, f"{document_id}:{chunk.index}")),
                vector=vector,
                payload={
                    "document_id": document_id,
                    "owner_user_id": owner_user_id,
                    "chunk_index": chunk.index,
                    "text": chunk.text,
                    "headings": chunk.headings,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def delete_document(self, document_id: str) -> None:
        if not self.client.collection_exists(self.collection):
            return
        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                )
            ),
        )

    def search(self, vector: list[float], owner_user_id: str, top_k: int) -> list[SearchHit]:
        self.ensure_collection()
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            query_filter=Filter(
                must=[FieldCondition(key="owner_user_id", match=MatchValue(value=owner_user_id))]
            ),
            with_payload=True,
        )
        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            text = payload.get("text")
            document_id = payload.get("document_id")
            if not isinstance(text, str) or not isinstance(document_id, str):
                continue
            headings = payload.get("headings") or []
            if not isinstance(headings, list):
                headings = []
            hits.append(
                SearchHit(
                    document_id=document_id,
                    chunk_index=int(payload.get("chunk_index") or 0),
                    text=text,
                    headings=[str(item) for item in headings],
                    score=float(point.score or 0),
                )
            )
        return hits
