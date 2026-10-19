"""Qdrant collection for document chunks.

Dense vectors are 1024-dimensional BGE-M3 embeddings with cosine distance.
Sparse vectors are BM25, produced on the Qdrant server by the `Qdrant/bm25`
model and stored with the IDF modifier. Hybrid search runs both queries,
always filtered to one user, and fuses the rankings with reciprocal rank fusion.

Qdrant 1.15 cannot add a sparse vector to a collection that was created with
only a dense vector. `migrate_to_hybrid` replaces that collection so the next
reindex can write both vectors. The Markdown in Postgres is the source for
that reindex.

`cloud_inference=True` tells the Python client to send the BM25 text to the
Qdrant server instead of embedding it locally. The server in this project is
the local `qdrant/qdrant:v1.15.4` image, which runs that model itself.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Document as Bm25Document,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)

from backend.chunking import TextChunk
from backend.config import Settings
from backend.fusion import reciprocal_rank_fusion

_NAMESPACE = uuid.UUID("8f3b1c2a-6d4e-5f70-9a1b-2c3d4e5f6071")
DENSE_NAME = "dense"
BM25_NAME = "bm25"
BM25_MODEL = "Qdrant/bm25"
_MIGRATE_LOCK = threading.Lock()


class VectorStoreError(Exception):
    """Qdrant could not store or read vectors."""


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    chunk_index: int
    text: str
    headings: list[str]
    score: float


def owner_filter(owner_user_id: str) -> Filter:
    """Match chunks that belong to one user."""
    return Filter(must=[FieldCondition(key="owner_user_id", match=MatchValue(value=owner_user_id))])


class VectorStore:
    def __init__(self, *, url: str, collection: str, dimension: int, timeout: float = 30) -> None:
        self.collection = collection
        self.dimension = dimension
        self.client = QdrantClient(
            url=url,
            timeout=timeout,
            prefer_grpc=False,
            cloud_inference=True,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> VectorStore:
        return cls(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dimension=settings.embedding_dimension,
        )

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self._create_hybrid()
            return
        if not self._is_hybrid():
            raise VectorStoreError(
                "The Qdrant collection has no BM25 index yet. Reindex documents to rebuild it."
            )
        self._check_dimension()

    def migrate_to_hybrid(self) -> bool:
        """Create the hybrid schema. Returns True when an older collection was replaced."""
        with _MIGRATE_LOCK:
            if not self.client.collection_exists(self.collection):
                self._create_hybrid()
                return False
            if self._is_hybrid():
                self._check_dimension()
                return False
            self.client.delete_collection(self.collection)
            self._create_hybrid()
            return True

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
        self.migrate_to_hybrid()
        self.delete_document(document_id)
        if not chunks:
            return
        points = [
            PointStruct(
                id=str(uuid.uuid5(_NAMESPACE, f"{document_id}:{chunk.index}")),
                vector={
                    DENSE_NAME: vector,
                    BM25_NAME: Bm25Document(text=chunk.text, model=BM25_MODEL),
                },
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

    def hybrid_search(
        self,
        *,
        query: str,
        vector: list[float],
        owner_user_id: str,
        top_k: int,
    ) -> list[SearchHit]:
        """Fuse a dense search and a BM25 search over one user's chunks."""
        if not self.client.collection_exists(self.collection):
            self._create_hybrid()
        if not self._is_hybrid():
            return self._dense_hits(vector, owner_user_id, top_k)
        self._check_dimension()
        user_filter = owner_filter(owner_user_id)
        candidates = max(top_k * 4, 20)
        dense = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            using=DENSE_NAME,
            query_filter=user_filter,
            limit=candidates,
            with_payload=True,
        )
        sparse = self.client.query_points(
            collection_name=self.collection,
            query=Bm25Document(text=query, model=BM25_MODEL),
            using=BM25_NAME,
            query_filter=user_filter,
            limit=candidates,
            with_payload=True,
        )
        dense_points = _owned_points(dense.points, owner_user_id)
        sparse_points = _owned_points(sparse.points, owner_user_id)
        fused = reciprocal_rank_fusion(
            [[str(point.id) for point in dense_points], [str(point.id) for point in sparse_points]]
        )
        by_id = {str(point.id): point for point in (*dense_points, *sparse_points)}
        hits: list[SearchHit] = []
        for point_id, score in fused[:top_k]:
            hit = _hit_from_point(by_id[point_id], score)
            if hit is not None:
                hits.append(hit)
        return hits

    def search_dense(self, *, vector: list[float], owner_user_id: str, top_k: int) -> list[SearchHit]:
        """Rank one user's chunks by the dense vector only."""
        if not self.client.collection_exists(self.collection):
            self._create_hybrid()
        if not self._is_hybrid():
            return self._dense_hits(vector, owner_user_id, top_k)
        self._check_dimension()
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            using=DENSE_NAME,
            query_filter=owner_filter(owner_user_id),
            limit=top_k,
            with_payload=True,
        )
        return _hits_from_response(response.points, owner_user_id)

    def search_bm25(self, *, query: str, owner_user_id: str, top_k: int) -> list[SearchHit]:
        """Rank one user's chunks by the BM25 sparse vector only."""
        if not self.client.collection_exists(self.collection) or not self._is_hybrid():
            raise VectorStoreError("BM25 search needs the hybrid collection.")
        self._check_dimension()
        response = self.client.query_points(
            collection_name=self.collection,
            query=Bm25Document(text=query, model=BM25_MODEL),
            using=BM25_NAME,
            query_filter=owner_filter(owner_user_id),
            limit=top_k,
            with_payload=True,
        )
        return _hits_from_response(response.points, owner_user_id)

    def _dense_hits(self, vector: list[float], owner_user_id: str, top_k: int) -> list[SearchHit]:
        """Search a collection that has not been rebuilt with BM25 yet."""
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=owner_filter(owner_user_id),
            limit=top_k,
            with_payload=True,
        )
        return _hits_from_response(response.points, owner_user_id)

    def _create_hybrid(self) -> None:
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={DENSE_NAME: VectorParams(size=self.dimension, distance=Distance.COSINE)},
            sparse_vectors_config={BM25_NAME: SparseVectorParams(modifier=Modifier.IDF)},
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

    def _is_hybrid(self) -> bool:
        info = self.client.get_collection(self.collection)
        sparse = info.config.params.sparse_vectors or {}
        return isinstance(sparse, dict) and BM25_NAME in sparse

    def _check_dimension(self) -> None:
        info = self.client.get_collection(self.collection)
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            params = vectors.get(DENSE_NAME)
            size = getattr(params, "size", None)
        else:
            size = getattr(vectors, "size", None)
        if size != self.dimension:
            raise VectorStoreError(
                f"Collection {self.collection} has dimension {size}, expected {self.dimension}."
            )


def _hits_from_response(points: list, owner_user_id: str) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for point in _owned_points(points, owner_user_id):
        hit = _hit_from_point(point, float(point.score or 0))
        if hit is not None:
            hits.append(hit)
    return hits


def _owned_points(points: list, owner_user_id: str) -> list:
    owned = []
    for point in points:
        payload = point.payload or {}
        if payload.get("owner_user_id") != owner_user_id:
            continue
        owned.append(point)
    return owned


def _hit_from_point(point, score: float) -> SearchHit | None:
    payload = point.payload or {}
    text = payload.get("text")
    document_id = payload.get("document_id")
    if not isinstance(text, str) or not isinstance(document_id, str):
        return None
    headings = payload.get("headings") or []
    if not isinstance(headings, list):
        headings = []
    return SearchHit(
        document_id=document_id,
        chunk_index=int(payload.get("chunk_index") or 0),
        text=text,
        headings=[str(item) for item in headings],
        score=float(score),
    )
