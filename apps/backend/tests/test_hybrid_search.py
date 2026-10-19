"""Hybrid search fuses dense and BM25 hits and keeps other users out."""

from types import SimpleNamespace

from backend.vector_store import VectorStore


class _Point:
    def __init__(self, point_id: str, owner: str, document_id: str, text: str, chunk: int = 0) -> None:
        self.id = point_id
        self.score = 0.4
        self.payload = {
            "owner_user_id": owner,
            "document_id": document_id,
            "chunk_index": chunk,
            "text": text,
            "headings": ["Orchard"],
        }


class _Client:
    def __init__(self, responses: list[list[_Point]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def collection_exists(self, name: str) -> bool:
        del name
        return True

    def get_collection(self, name: str) -> SimpleNamespace:
        del name
        vectors = {"dense": SimpleNamespace(size=4)}
        sparse = {"bm25": SimpleNamespace()}
        params = SimpleNamespace(vectors=vectors, sparse_vectors=sparse)
        return SimpleNamespace(config=SimpleNamespace(params=params))

    def query_points(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(points=self._responses.pop(0))


def _store(client: _Client) -> VectorStore:
    store = VectorStore(url="http://127.0.0.1:6333", collection="documents", dimension=4)
    store.client = client
    return store


def test_queries_are_filtered_to_the_caller_and_fused() -> None:
    dense = [
        _Point("b", "user-a", "doc-b", "harbor"),
        _Point("a", "user-a", "doc-a", "crimson apple"),
    ]
    sparse = [
        _Point("a", "user-a", "doc-a", "crimson apple"),
        _Point("c", "user-a", "doc-c", "tide"),
    ]
    client = _Client([dense, sparse])
    hits = _store(client).hybrid_search(query="crimson apple", vector=[0.1, 0.2, 0.3, 0.4], owner_user_id="user-a", top_k=3)

    assert [hit.document_id for hit in hits] == ["doc-a", "doc-b", "doc-c"]
    assert hits[0].text == "crimson apple"
    assert len(client.calls) == 2
    assert client.calls[0]["using"] == "dense"
    assert client.calls[1]["using"] == "bm25"
    for call in client.calls:
        condition = call["query_filter"].must[0]
        assert condition.key == "owner_user_id"
        assert condition.match.value == "user-a"


def test_points_for_someone_else_are_dropped() -> None:
    foreign = [_Point("x", "user-b", "doc-b", "secret")]
    client = _Client([foreign, []])
    hits = _store(client).hybrid_search(query="secret", vector=[0.1, 0.2, 0.3, 0.4], owner_user_id="user-a", top_k=5)
    assert hits == []
    assert client.calls[0]["query_filter"].must[0].match.value == "user-a"
