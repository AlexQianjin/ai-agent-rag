"""LLM-as-judge over the same OpenAI-compatible endpoint as the agent.

One call scores faithfulness, relevance, and refusal. The criteria live in
`prompts/`. Citation accuracy is computed from the cited source number and
does not go through the judge.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from evals.dataset import Case
from evals.retrieval import EvalError

PROMPTS = Path(__file__).resolve().parent / "prompts"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class JudgeScore:
    faithfulness: float
    relevance: float
    refused: bool
    notes: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def load_criteria() -> str:
    names = ("faithfulness.md", "relevance.md", "refusal.md", "output.md")
    parts = []
    for name in names:
        path = PROMPTS / name
        if not path.is_file():
            raise EvalError(f"Missing judge prompt {path}.")
        parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def judge_messages(case: Case, sources: list[dict], answer: str, criteria: str) -> list[dict[str, str]]:
    facts = "\n".join(f"- {fact}" for fact in case.key_facts) or "- (none; the passages may not contain an answer)"
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        blocks.append(
            f"[{index}] {source.get('document_name')} chunk {source.get('chunk_index')}\n{source.get('text', '')}"
        )
    passages = "\n\n".join(blocks) if blocks else "No passages."
    user = (
        f"Question:\n{case.question}\n\n"
        f"Key facts:\n{facts}\n\n"
        f"Passages:\n{passages}\n\n"
        f"Answer:\n{answer}"
    )
    return [
        {"role": "system", "content": criteria},
        {"role": "user", "content": user},
    ]


def parse_judge(text: str) -> tuple[float, float, bool, str]:
    """Read the judge JSON. Fenced blocks are stripped first."""
    stripped = text.strip()
    stripped = _FENCE.sub("", stripped).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise EvalError(f"Judge did not return JSON: {stripped[:240]}") from exc
    if not isinstance(data, dict):
        raise EvalError("Judge JSON must be an object.")
    try:
        faithfulness = _unit(data["faithfulness"])
        relevance = _unit(data["relevance"])
        refused = data["refused"]
    except (KeyError, TypeError, ValueError) as exc:
        raise EvalError(f"Judge JSON is missing a score: {data}") from exc
    if not isinstance(refused, bool):
        raise EvalError("Judge field refused must be a boolean.")
    notes = data.get("notes", "")
    if not isinstance(notes, str):
        notes = str(notes)
    return faithfulness, relevance, refused, notes


def score_answer(
    case: Case,
    sources: list[dict],
    answer: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    criteria: str,
) -> JudgeScore:
    from evals.answer import chat_completion

    message, usage = chat_completion(
        judge_messages(case, sources, answer, criteria),
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    faithfulness, relevance, refused, notes = parse_judge(message)
    return JudgeScore(
        faithfulness=faithfulness,
        relevance=relevance,
        refused=refused,
        notes=notes,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


def _unit(value: object) -> float:
    number = float(value)  # type: ignore[arg-type]
    if number < 0 or number > 1:
        raise ValueError(number)
    return number
