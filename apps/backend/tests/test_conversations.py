"""Conversation CRUD, owner isolation, and the streamed chat turn."""

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.db import SessionLocal
from backend.main import app
from backend.models import Conversation, Document, Message


def test_crud_isolates_owners_and_cascades_messages(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.documents.schedule_indexing", lambda document_id: None)
    owner = _sign_up(f"chat-owner-{uuid.uuid4().hex[:8]}@example.com")
    stranger = _sign_up(f"chat-stranger-{uuid.uuid4().hex[:8]}@example.com")
    notes = tmp_path / "notes.txt"
    notes.write_text("The crimson apple ripens beside the stone wall.\n", encoding="utf-8")

    with TestClient(app) as client:
        created = client.post("/conversations", json={}, headers={"cookie": owner})
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        assert created.json()["title"] == "New conversation"

        hidden = client.get(f"/conversations/{conversation_id}", headers={"cookie": stranger})
        assert hidden.status_code == 404
        assert client.get("/conversations", headers={"cookie": stranger}).json()["conversations"] == []

        renamed = client.patch(
            f"/conversations/{conversation_id}",
            json={"title": "Orchard questions"},
            headers={"cookie": owner},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Orchard questions"
        assert client.patch(
            f"/conversations/{conversation_id}",
            json={"title": "nope"},
            headers={"cookie": stranger},
        ).status_code == 404

        uploaded = client.post(
            "/documents",
            data={"conversation_id": conversation_id},
            files={"file": ("notes.txt", notes.read_bytes(), "text/plain")},
            headers={"cookie": owner},
        )
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["id"]
        assert uploaded.json()["conversation_id"] == conversation_id
        stranger_upload = client.post(
            "/documents",
            data={"conversation_id": conversation_id},
            files={"file": ("notes.txt", notes.read_bytes(), "text/plain")},
            headers={"cookie": stranger},
        )
        assert stranger_upload.status_code == 404

        detail = client.get(f"/conversations/{conversation_id}", headers={"cookie": owner})
        assert detail.status_code == 200
        assert detail.json()["documents"][0]["id"] == document_id

        removed = client.delete(f"/conversations/{conversation_id}", headers={"cookie": owner})
        assert removed.status_code == 204
        assert client.get(f"/conversations/{conversation_id}", headers={"cookie": owner}).status_code == 404
        assert client.delete(f"/conversations/{conversation_id}", headers={"cookie": stranger}).status_code == 404

    db = SessionLocal()
    try:
        assert db.get(Conversation, conversation_id) is None
        assert db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all() == []
        document = db.get(Document, document_id)
        assert document is not None
        assert document.conversation_id is None
    finally:
        db.close()


def test_stream_persists_messages_and_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_turn(*, user_id: str, query: str, history: list[dict[str, str]], deps=None):
        del deps
        assert user_id
        assert query == "Where is the apple?"
        assert history == []
        yield {"type": "thinking", "status": "Thinking…"}
        yield {"type": "searching", "status": "Searching documents…"}
        sources = [
            {
                "document_id": "doc-1",
                "document_name": "notes.txt",
                "chunk_index": 0,
                "text": "The crimson apple ripens beside the stone wall.",
                "headings": ["Orchard"],
                "score": 0.032,
            }
        ]
        yield {"type": "retrieved", "status": "Found 1 passages", "sources": sources}
        yield {"type": "token", "delta": "Beside the wall "}
        yield {"type": "token", "delta": "[1]."}

    monkeypatch.setattr("backend.conversations.stream_turn", fake_turn)
    owner = _sign_up(f"chat-stream-{uuid.uuid4().hex[:8]}@example.com")
    stranger = _sign_up(f"chat-stream-other-{uuid.uuid4().hex[:8]}@example.com")

    with TestClient(app) as client:
        conversation_id = client.post("/conversations", json={}, headers={"cookie": owner}).json()["id"]
        denied = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": "Where is the apple?"},
            headers={"cookie": stranger},
        )
        assert denied.status_code == 404

        response = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": "Where is the apple?"},
            headers={"cookie": owner},
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.text
        assert "event: searching" in body
        assert "Searching documents…" in body
        assert "event: retrieved" in body
        assert "notes.txt" in body
        assert "event: token" in body
        assert "Beside the wall" in body
        assert "event: done" in body

        detail = client.get(f"/conversations/{conversation_id}", headers={"cookie": owner}).json()
        assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
        assert detail["messages"][0]["content"] == "Where is the apple?"
        answer = detail["messages"][1]
        assert answer["content"] == "Beside the wall [1]."
        assert answer["citations"][0]["document_name"] == "notes.txt"
        assert answer["citations"][0]["chunk_index"] == 0
        assert detail["title"] == "Where is the apple?"

        listing = client.get("/conversations", headers={"cookie": owner}).json()["conversations"]
        assert listing[0]["id"] == conversation_id


@pytest.fixture(autouse=True)
def _clean_conversations() -> None:
    yield
    db = SessionLocal()
    try:
        db.execute(delete(Message))
        db.execute(delete(Document))
        db.execute(delete(Conversation))
        db.commit()
    finally:
        db.close()


def _sign_up(email: str) -> str:
    auth_url = os.environ.get("AUTH_URL", "http://127.0.0.1:3001").rstrip("/")
    response = httpx.post(
        f"{auth_url}/api/auth/sign-up/email",
        json={"name": "Chat Tester", "email": email, "password": "password123"},
        headers={"Origin": "http://localhost:5173"},
        timeout=15,
    )
    assert response.status_code == 200, response.text
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        if pair.startswith("better-auth.session_token="):
            return pair
    raise AssertionError("sign-up did not set a session cookie")
