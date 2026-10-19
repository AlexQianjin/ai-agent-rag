"""Embedding client batching, retries, and dimension checks."""

import httpx
import pytest

from backend.embeddings import EmbeddingClient, EmbeddingError

DIMENSION = 4


def _client(handler, **kwargs) -> EmbeddingClient:
    return EmbeddingClient(
        base_url="http://embeddings.test",
        model="bge-m3",
        dimension=DIMENSION,
        timeout=1,
        batch_size=kwargs.pop("batch_size", 2),
        retries=kwargs.pop("retries", 3),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
        **kwargs,
    )


def _vectors(count: int) -> list[list[float]]:
    return [[float(index)] * DIMENSION for index in range(count)]


def test_batches_posts_and_checks_dimension() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        import json

        payload = json.loads(body)
        calls.append(payload)
        assert request.url.path == "/api/embed"
        assert payload["model"] == "bge-m3"
        return httpx.Response(200, json={"embeddings": _vectors(len(payload["input"]))})

    vectors = _client(handler, batch_size=2).embed(["one", "two", "three", "four", "five"])

    assert [len(item["input"]) for item in calls] == [2, 2, 1]
    assert len(vectors) == 5
    assert all(len(vector) == DIMENSION for vector in vectors)


def test_retries_server_errors_then_returns_vectors() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"embeddings": _vectors(1)})

    vectors = _client(handler, retries=3).embed(["hello"])

    assert attempts["count"] == 3
    assert vectors == [[0.0, 0.0, 0.0, 0.0]]


def test_rejects_wrong_dimension_without_retry_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0, 2.0]]})

    with pytest.raises(EmbeddingError, match="1024|4-dimensional|dimensional"):
        _client(handler, retries=2).embed(["hello"])


def test_timeout_becomes_an_embedding_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with pytest.raises(EmbeddingError, match="unavailable"):
        _client(handler, retries=2).embed(["hello"])
