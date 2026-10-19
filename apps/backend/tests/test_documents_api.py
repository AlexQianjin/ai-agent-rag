"""Upload flow against PostgreSQL and a live Better Auth session."""

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.config import get_settings
from backend.db import SessionLocal
from backend.indexing import schedule_indexing
from backend.main import app
from backend.models import Document


def test_upload_lists_and_hides_other_owners(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    indexed: list[str] = []
    monkeypatch.setattr("backend.documents.schedule_indexing", lambda document_id: indexed.append(document_id))

    owner = _sign_up(f"owner-{uuid.uuid4().hex[:8]}@example.com")
    stranger = _sign_up(f"stranger-{uuid.uuid4().hex[:8]}@example.com")
    notes = tmp_path / "notes.txt"
    notes.write_text("Hello from the upload\n", encoding="utf-8")

    with TestClient(app) as client:
        rejected = client.post(
            "/documents",
            files={"file": ("notes.txt", notes.read_bytes(), "text/plain")},
        )
        assert rejected.status_code == 401

        created = client.post(
            "/documents",
            files={"file": ("notes.txt", notes.read_bytes(), "text/plain")},
            headers={"cookie": owner},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "pending"
        assert body["mime_type"] == "text/plain"
        document_id = body["id"]

        detail = client.get(f"/documents/{document_id}", headers={"cookie": owner})
        assert detail.status_code == 200
        finished = detail.json()
        assert finished["status"] == "ready"
        assert finished["markdown"] == "Hello from the upload\n"
        assert indexed == [document_id]

        listing = client.get("/documents", headers={"cookie": owner})
        assert listing.status_code == 200
        assert any(item["id"] == document_id for item in listing.json()["documents"])

        hidden = client.get(f"/documents/{document_id}", headers={"cookie": stranger})
        assert hidden.status_code == 404

        stranger_list = client.get("/documents", headers={"cookie": stranger})
        assert stranger_list.status_code == 200
        assert stranger_list.json()["documents"] == []

        oversized = b"x" * (get_settings().max_upload_bytes + 1)
        too_big = client.post(
            "/documents",
            files={"file": ("big.txt", oversized, "text/plain")},
            headers={"cookie": owner},
        )
        assert too_big.status_code == 413

        bad_type = client.post(
            "/documents",
            files={"file": ("pic.png", b"not-an-image", "image/png")},
            headers={"cookie": owner},
        )
        assert bad_type.status_code == 400

    assert schedule_indexing("unused") is None


@pytest.fixture(autouse=True)
def _clean_documents() -> None:
    yield
    db = SessionLocal()
    try:
        db.execute(delete(Document))
        db.commit()
    finally:
        db.close()


def _sign_up(email: str) -> str:
    auth_url = os.environ.get("AUTH_URL", "http://127.0.0.1:3001").rstrip("/")
    response = httpx.post(
        f"{auth_url}/api/auth/sign-up/email",
        json={"name": "Document Tester", "email": email, "password": "password123"},
        headers={"Origin": "http://localhost:5173"},
        timeout=15,
    )
    assert response.status_code == 200, response.text
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        if pair.startswith("better-auth.session_token="):
            return pair
    raise AssertionError("sign-up did not set a session cookie")
