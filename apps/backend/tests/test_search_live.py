"""Upload, index, and search against Ollama and Qdrant when both are up."""

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app


def test_owner_search_hides_chunks_from_other_users() -> None:
    _require_live_stack()
    owner = _sign_up(f"owner-{uuid.uuid4().hex[:8]}@example.com")
    stranger = _sign_up(f"stranger-{uuid.uuid4().hex[:8]}@example.com")
    markdown = """# Orchard

The crimson apple ripens beside the stone wall.

# Harbor

The blue fishing boat waits at the pier.
"""
    with TestClient(app) as client:
        created = client.post(
            "/documents",
            files={"file": ("notes.md", markdown.encode(), "text/markdown")},
            headers={"cookie": owner},
        )
        assert created.status_code == 201, created.text
        created.json()
        document_id = created.json()["id"]
        detail = client.get(f"/documents/{document_id}", headers={"cookie": owner})
        body = detail.json()
        assert body["index_status"] == "indexed", body

        apple = client.post(
            "/search",
            json={"query": "crimson apple on the wall", "top_k": 2},
            headers={"cookie": owner},
        )
        assert apple.status_code == 200, apple.text
        top = apple.json()["results"][0]
        assert top["document_id"] == document_id
        assert "crimson apple" in top["text"]
        assert "Orchard" in top["headings"]

        hidden = client.post(
            "/search",
            json={"query": "crimson apple on the wall", "top_k": 2},
            headers={"cookie": stranger},
        )
        assert hidden.status_code == 200
        assert hidden.json()["results"] == []

        removed = client.delete(f"/documents/{document_id}", headers={"cookie": owner})
        assert removed.status_code == 204
        assert client.get(f"/documents/{document_id}", headers={"cookie": owner}).status_code == 404
        after = client.post(
            "/search",
            json={"query": "crimson apple on the wall", "top_k": 2},
            headers={"cookie": owner},
        )
        assert after.status_code == 200
        assert after.json()["results"] == []


def _require_live_stack() -> None:
    embedding = os.environ.get("EMBEDDING_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    qdrant = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
    try:
        tags = httpx.get(f"{embedding}/api/tags", timeout=3)
        ready = httpx.get(f"{qdrant}/readyz", timeout=3)
    except httpx.HTTPError as exc:
        pytest.skip(f"Ollama or Qdrant is not reachable: {exc}")
    if tags.status_code != 200 or ready.status_code != 200:
        pytest.skip("Ollama or Qdrant is not ready")
    names = [item.get("name", "") for item in tags.json().get("models", [])]
    if not any(name.split(":")[0] == "bge-m3" for name in names):
        pytest.skip("bge-m3 is not pulled")


def _sign_up(email: str) -> str:
    auth_url = os.environ.get("AUTH_URL", "http://127.0.0.1:3001").rstrip("/")
    response = httpx.post(
        f"{auth_url}/api/auth/sign-up/email",
        json={"name": "Search Tester", "email": email, "password": "password123"},
        headers={"Origin": "http://localhost:5173"},
        timeout=15,
    )
    assert response.status_code == 200, response.text
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        if pair.startswith("better-auth.session_token="):
            return pair
    raise AssertionError("sign-up did not set a session cookie")
