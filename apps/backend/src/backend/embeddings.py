"""Embed text with Ollama's native batch endpoint.

`POST {EMBEDDING_BASE_URL}/api/embed` takes a list of strings and returns the
vectors in the same order. Ollama's OpenAI-compatible `/v1/embeddings` route
is a shim, and its batch behavior has lagged the native API. The native call
is the one that is meant to embed a batch in one request, which is what
indexing needs. Point `EMBEDDING_BASE_URL` at another Ollama, including one
on the host, without changing the client.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from backend.config import Settings


class EmbeddingError(Exception):
    """The embedding service could not return vectors."""


class EmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimension: int,
        timeout: float = 60,
        batch_size: int = 16,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if dimension < 1:
            raise ValueError("Embedding dimension must be positive.")
        if batch_size < 1:
            raise ValueError("Batch size must be positive.")
        if retries < 1:
            raise ValueError("Retries must be at least 1.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self.timeout = timeout
        self.batch_size = batch_size
        self.retries = retries
        self._transport = transport
        self._sleeper = sleeper

    @classmethod
    def from_settings(cls, settings: Settings) -> EmbeddingClient:
        return cls(
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            timeout=settings.embedding_timeout_seconds,
            batch_size=settings.embedding_batch_size,
            retries=settings.embedding_retries,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size]))
        if len(vectors) != len(texts):
            raise EmbeddingError("The embedding service returned the wrong number of vectors.")
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                payload = self._post(texts)
                return self._vectors(payload, expected=len(texts))
            except EmbeddingError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt + 1 < self.retries:
                self._sleeper(min(2**attempt, 8))
        raise EmbeddingError("Embedding service is unavailable.") from last_error

    def _post(self, texts: list[str]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            response = client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()
        if response.status_code >= 400:
            raise EmbeddingError("The embedding service rejected the request.")
        body = response.json()
        if not isinstance(body, dict):
            raise EmbeddingError("The embedding service returned an unexpected response.")
        return body

    def _vectors(self, payload: dict[str, Any], *, expected: int) -> list[list[float]]:
        raw = payload.get("embeddings")
        if not isinstance(raw, list) or len(raw) != expected:
            raise EmbeddingError("The embedding service returned the wrong number of vectors.")
        vectors: list[list[float]] = []
        for item in raw:
            if not isinstance(item, list) or len(item) != self.dimension:
                raise EmbeddingError(
                    f"Expected {self.dimension}-dimensional vectors from {self.model}."
                )
            vectors.append([float(value) for value in item])
        return vectors
