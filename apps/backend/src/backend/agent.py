"""LangGraph agent that answers from the signed-in user's documents.

The graph is a straight line: recall, retrieve, answer. Recall is empty until
mem0 is connected. Retrieve runs hybrid search. Answer streams tokens from
Grok through the xAI OpenAI-compatible API and is asked to cite the retrieved
passages by document name and chunk.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from backend.config import get_settings
from backend.models import Document


class AgentError(Exception):
    """The agent could not complete a turn."""


class AgentState(TypedDict, total=False):
    user_id: str
    query: str
    history: list[dict[str, str]]
    memories: list[str]
    sources: list[dict]
    answer: str


@dataclass
class AgentDeps:
    retrieve: Callable[[str, str, int], list[dict]]
    complete: Callable[[list[dict[str, str]]], Iterator[str]]
    recall: Callable[[str, str], list[str]]
    top_k: int = 5


def recall_memories(user_id: str, query: str) -> list[str]:
    """Load memories for this user.

    This returns nothing today. A mem0 store can replace this function later.
    The answer step already includes `memories` in the prompt.
    """
    del user_id, query
    return []


def retrieve_for_user(user_id: str, query: str, top_k: int) -> list[dict]:
    """Hybrid-search this user's chunks and attach document names."""
    from backend.embeddings import EmbeddingClient
    from backend.vector_store import VectorStore

    settings = get_settings()
    vector = EmbeddingClient.from_settings(settings).embed([query])[0]
    hits = VectorStore.from_settings(settings).hybrid_search(
        query=query,
        vector=vector,
        owner_user_id=user_id,
        top_k=top_k,
    )
    names = _document_names(user_id, [hit.document_id for hit in hits])
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


def default_complete(messages: list[dict[str, str]]) -> Iterator[str]:
    """Stream an answer from Grok through the OpenAI-compatible xAI endpoint."""
    settings = get_settings()
    if not settings.xai_api_key.strip():
        raise AgentError("XAI_API_KEY is not set.")
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.xai_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        streaming=True,
    )
    converted = []
    for message in messages:
        content = message["content"]
        role = message["role"]
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    for chunk in llm.stream(converted):
        text = _chunk_text(chunk.content)
        if text:
            yield text


def default_deps() -> AgentDeps:
    settings = get_settings()
    return AgentDeps(
        retrieve=retrieve_for_user,
        complete=default_complete,
        recall=recall_memories,
        top_k=settings.retrieval_top_k,
    )


def build_graph(deps: AgentDeps):
    """Compile the recall -> retrieve -> answer graph."""

    def recall(state: AgentState) -> dict:
        _emit({"type": "thinking", "status": "Thinking…"})
        memories = deps.recall(state["user_id"], state["query"])
        return {"memories": memories}

    def retrieve(state: AgentState) -> dict:
        _emit({"type": "searching", "status": "Searching documents…"})
        sources = deps.retrieve(state["user_id"], state["query"], deps.top_k)
        _emit(
            {
                "type": "retrieved",
                "status": f"Found {len(sources)} passages",
                "sources": sources,
            }
        )
        return {"sources": sources}

    def answer(state: AgentState) -> dict:
        _emit({"type": "thinking", "status": "Writing an answer…"})
        parts: list[str] = []
        for delta in deps.complete(prompt_messages(state)):
            parts.append(delta)
            _emit({"type": "token", "delta": delta})
        return {"answer": "".join(parts)}

    graph = StateGraph(AgentState)
    graph.add_node("recall", recall)
    graph.add_node("retrieve", retrieve)
    graph.add_node("answer", answer)
    graph.add_edge(START, "recall")
    graph.add_edge("recall", "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


def stream_turn(
    *,
    user_id: str,
    query: str,
    history: list[dict[str, str]],
    deps: AgentDeps | None = None,
) -> Iterator[dict]:
    """Run one turn and yield progress events as the graph produces them."""
    graph = build_graph(deps or default_deps())
    state: AgentState = {
        "user_id": user_id,
        "query": query,
        "history": history,
        "memories": [],
        "sources": [],
        "answer": "",
    }
    yield from graph.stream(state, stream_mode="custom")


def prompt_messages(state: AgentState) -> list[dict[str, str]]:
    """Build the chat messages for the answer step, including citations."""
    sources = state.get("sources") or []
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        heading = " / ".join(source.get("headings") or [])
        where = f"{source.get('document_name', 'Document')} chunk {source.get('chunk_index', 0)}"
        if heading:
            where = f"{where} ({heading})"
        blocks.append(f"[{index}] {where}\n{source.get('text', '')}")
    context = "\n\n".join(blocks) if blocks else "No matching passages."
    system = (
        "You answer questions from the user's documents. "
        "Cite a passage inline as [n], using the source number. "
        "Each source line names the document and the chunk. "
        "If the passages do not contain the answer, say so. "
        "Do not invent a source."
    )
    memories = state.get("memories") or []
    if memories:
        system = system + "\n\nMemories:\n" + "\n".join(memories)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Sources:\n{context}"},
    ]
    for item in state.get("history") or []:
        role = item.get("role", "user")
        if role not in {"user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": item.get("content", "")})
    messages.append({"role": "user", "content": state.get("query", "")})
    return messages


def _document_names(user_id: str, document_ids: list[str]) -> dict[str, str]:
    if not document_ids:
        return {}
    from backend.db import SessionLocal

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Document).where(Document.owner_user_id == user_id, Document.id.in_(document_ids))
        ).all()
        return {row.id: row.filename for row in rows}
    finally:
        db.close()


def _emit(payload: dict) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(payload)


def _chunk_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""
