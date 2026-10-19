"""The chat graph retrieves, then cites, without calling a live model."""

import pytest

from backend.agent import AgentDeps, AgentError, default_complete, stream_turn
from backend.config import get_settings


def test_graph_searches_then_cites_sources() -> None:
    seen: dict[str, object] = {}

    def recall(user_id: str, query: str) -> list[str]:
        assert user_id == "user-1"
        assert query == "Where is the apple?"
        return ["The user prefers a short answer."]

    def retrieve(user_id: str, query: str, top_k: int) -> list[dict]:
        seen["user_id"] = user_id
        seen["query"] = query
        seen["top_k"] = top_k
        return [
            {
                "document_id": "doc-1",
                "document_name": "Orchard.md",
                "chunk_index": 2,
                "text": "The crimson apple ripens beside the stone wall.",
                "headings": ["Orchard"],
                "score": 0.03,
            }
        ]

    def complete(messages: list[dict[str, str]]):
        blob = "\n".join(message["content"] for message in messages)
        assert "Orchard.md chunk 2" in blob
        assert "The user prefers a short answer." in blob
        assert "Where is the apple?" in blob
        yield "Beside the wall "
        yield "[1]."

    deps = AgentDeps(retrieve=retrieve, complete=complete, recall=recall, top_k=4)
    events = list(stream_turn(user_id="user-1", query="Where is the apple?", history=[], deps=deps))
    kinds = [event["type"] for event in events]
    assert kinds[:4] == ["thinking", "searching", "retrieved", "thinking"]
    assert events[2]["sources"][0]["document_name"] == "Orchard.md"
    assert events[2]["sources"][0]["chunk_index"] == 2
    answer = "".join(event["delta"] for event in events if event["type"] == "token")
    assert answer == "Beside the wall [1]."
    assert seen == {"user_id": "user-1", "query": "Where is the apple?", "top_k": 4}


def test_missing_api_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "")
    # Settings still requires a URL, but this test never opens a connection.
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/unused")
    get_settings.cache_clear()
    try:
        with pytest.raises(AgentError, match="XAI_API_KEY"):
            list(default_complete([{"role": "user", "content": "Hello"}]))
    finally:
        get_settings.cache_clear()
