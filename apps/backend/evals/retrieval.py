"""Index the golden documents and compare dense, BM25, and hybrid search.

The collection is deleted and recreated on every run. It is not the
`documents` collection the app uses for uploaded files.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.chunking import chunk_markdown
from backend.conversion import convert_to_markdown
from backend.embeddings import EmbeddingClient
from backend.vector_store import SearchHit, VectorStore

from evals.dataset import DOCUMENTS_DIR, Case

EVAL_OWNER = "eval-user"
_DOC_NAMESPACE = uuid.UUID("c1e0a11e-5e15-5a11-9e11-000000000001")
_APP_COLLECTION = "documents"


class EvalError(Exception):
    """The eval could not index or score the golden set."""


@dataclass(frozen=True)
class IndexedDocument:
    filename: str
    document_id: str
    chunk_count: int


def document_id_for(filename: str) -> str:
    return str(uuid.uuid5(_DOC_NAMESPACE, filename))


def index_documents(
    store: VectorStore,
    embedder: EmbeddingClient,
    documents_dir: Path | None = None,
) -> list[IndexedDocument]:
    """Replace the eval collection with the sample documents."""
    if store.collection == _APP_COLLECTION:
        raise EvalError(
            "Refusing to reset the documents collection. Set EVAL_COLLECTION to a separate name."
        )
    folder = documents_dir or DOCUMENTS_DIR
    paths = sorted(path for path in folder.iterdir() if path.is_file() and not path.name.startswith("."))
    if not paths:
        raise EvalError(f"No sample documents in {folder}.")
    if store.client.collection_exists(store.collection):
        store.client.delete_collection(store.collection)
    indexed: list[IndexedDocument] = []
    for path in paths:
        markdown = convert_to_markdown(path, path.name)
        chunks = chunk_markdown(markdown)
        if not chunks:
            raise EvalError(f"{path.name} produced no chunks.")
        vectors = embedder.embed([chunk.text for chunk in chunks])
        document_id = document_id_for(path.name)
        store.replace_document(
            document_id=document_id,
            owner_user_id=EVAL_OWNER,
            chunks=chunks,
            vectors=vectors,
        )
        indexed.append(IndexedDocument(path.name, document_id, len(chunks)))
        print(f"indexed {path.name} ({len(chunks)} chunks)")
    return indexed


def names_by_id(documents: list[IndexedDocument]) -> dict[str, str]:
    return {item.document_id: item.filename for item in documents}


def search_hits(
    store: VectorStore,
    *,
    mode: str,
    query: str,
    vector: list[float],
    top_k: int,
) -> list[SearchHit]:
    if mode == "dense":
        return store.search_dense(vector=vector, owner_user_id=EVAL_OWNER, top_k=top_k)
    if mode == "bm25":
        return store.search_bm25(query=query, owner_user_id=EVAL_OWNER, top_k=top_k)
    if mode == "hybrid":
        return store.hybrid_search(query=query, vector=vector, owner_user_id=EVAL_OWNER, top_k=top_k)
    raise EvalError(f"Unknown search mode {mode}.")


def labeled_hits(hits: list[SearchHit], names: dict[str, str]) -> list[tuple[str, int]]:
    labeled: list[tuple[str, int]] = []
    for hit in hits:
        name = names.get(hit.document_id)
        if name is None:
            continue
        labeled.append((name, hit.chunk_index))
    return labeled


def retrieve_sources(
    store: VectorStore,
    embedder: EmbeddingClient,
    names: dict[str, str],
    query: str,
    top_k: int,
) -> list[dict]:
    """Hybrid search in the shape the agent prompt expects."""
    vector = embedder.embed([query])[0]
    hits = store.hybrid_search(query=query, vector=vector, owner_user_id=EVAL_OWNER, top_k=top_k)
    sources: list[dict] = []
    for hit in hits:
        name = names.get(hit.document_id)
        if name is None:
            continue
        sources.append(
            {
                "document_id": hit.document_id,
                "document_name": name,
                "chunk_index": hit.chunk_index,
                "text": hit.text,
                "headings": hit.headings,
                "score": hit.score,
            }
        )
    return sources


def answerable(cases: list[Case]) -> list[Case]:
    return [case for case in cases if not case.unanswerable]
