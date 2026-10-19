"""Run one agent turn and score the answer.

The graph is the production graph. Retrieval and the chat call are injected,
so the eval does not read Postgres and can point the model at another
OpenAI-compatible server.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from typing import Any

import httpx

from backend.agent import AgentDeps, stream_turn
from backend.embeddings import EmbeddingClient
from backend.vector_store import VectorStore

from evals.dataset import Case
from evals.judge import load_criteria, score_answer
from evals.retrieval import EVAL_OWNER, EvalError, retrieve_sources

_CITE = re.compile(r"\[(\d+)\]")


def chat_completion(
    messages: list[dict[str, str]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
) -> tuple[str, dict[str, int | None]]:
    """Non-streaming chat completion. Returns the text and token counts."""
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise EvalError(f"Chat completion request failed: {exc}") from exc
    if response.status_code >= 400:
        raise EvalError(f"Chat completion failed ({response.status_code}): {response.text[:240]}")
    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise EvalError("Chat completion response had no message.") from exc
    if not isinstance(content, str):
        content = str(content)
    raw = data.get("usage") or {}
    usage = {
        "prompt_tokens": _optional_int(raw.get("prompt_tokens")),
        "completion_tokens": _optional_int(raw.get("completion_tokens")),
        "total_tokens": _optional_int(raw.get("total_tokens")),
    }
    return content, usage


def citation_correct(answer: str, sources: list[dict], document: str, chunk: int) -> bool:
    """True when some [n] citation points at the expected document and chunk."""
    for number in _CITE.findall(answer):
        index = int(number) - 1
        if index < 0 or index >= len(sources):
            continue
        source = sources[index]
        if source.get("document_name") == document and int(source.get("chunk_index", -1)) == chunk:
            return True
    return False


def run_turn(
    case: Case,
    *,
    store: VectorStore,
    embedder: EmbeddingClient,
    names: dict[str, str],
    top_k: int,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
) -> dict[str, Any]:
    """Answer one question with the LangGraph agent. Record latency and tokens."""
    usage: dict[str, int | None] = {}

    def retrieve(user_id: str, query: str, limit: int) -> list[dict]:
        del user_id
        return retrieve_sources(store, embedder, names, query, limit)

    def complete(messages: list[dict[str, str]]) -> Iterator[str]:
        # The agent builds the prompt; the eval records usage from this call.
        text, call_usage = chat_completion(
            messages,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )
        usage.update(call_usage)
        yield text

    deps = AgentDeps(retrieve=retrieve, complete=complete, recall=lambda _user, _query: [], top_k=top_k)
    started = time.perf_counter()
    sources: list[dict] = []
    parts: list[str] = []
    for event in stream_turn(user_id=EVAL_OWNER, query=case.question, history=[], deps=deps):
        if event.get("type") == "retrieved":
            sources = list(event.get("sources") or [])
        elif event.get("type") == "token":
            parts.append(str(event.get("delta") or ""))
    elapsed_ms = (time.perf_counter() - started) * 1000
    answer = "".join(parts)
    cited = None
    if not case.unanswerable and case.expected_document is not None and case.expected_chunk is not None:
        cited = citation_correct(answer, sources, case.expected_document, case.expected_chunk)
    return {
        "answer": answer,
        "sources": sources,
        "citation_correct": cited,
        "answer_latency_ms": elapsed_ms,
        "answer_tokens": usage,
    }


def judge_turn(
    case: Case,
    answer: str,
    sources: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    criteria: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    score = score_answer(
        case,
        sources,
        answer,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        criteria=criteria if criteria is not None else load_criteria(),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    expected_refusal = case.unanswerable
    return {
        "faithfulness": score.faithfulness,
        "relevance": score.relevance,
        "refused": score.refused,
        "refusal_correct": score.refused == expected_refusal,
        "notes": score.notes,
        "judge_latency_ms": elapsed_ms,
        "judge_tokens": {
            "prompt_tokens": score.prompt_tokens,
            "completion_tokens": score.completion_tokens,
            "total_tokens": score.total_tokens,
        },
    }


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
