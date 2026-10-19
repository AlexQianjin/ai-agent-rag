"""Seam for the retrieval index.

Chunking, embeddings, and Qdrant are intentionally not implemented. Call
`schedule_indexing` after a document's Markdown is stored so that work has
one place to land later.
"""


def schedule_indexing(document_id: str) -> None:
    """Record that a ready document can be indexed.

    The document id is accepted so a future worker can load the Markdown
    without changing the conversion flow. This function does not read the
    database or call a vector store.
    """
    del document_id
