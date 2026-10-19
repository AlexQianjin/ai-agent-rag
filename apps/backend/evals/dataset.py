"""Load the golden question set.

A case is one question. Answerable cases name the document and chunk that
contain the answer, plus the facts a correct answer should include.
Unanswerable cases set `unanswerable: true` and omit the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "data" / "cases.yaml"
DOCUMENTS_DIR = ROOT / "data" / "documents"


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    expected_document: str | None
    expected_chunk: int | None
    key_facts: tuple[str, ...]
    unanswerable: bool


def load_cases(path: Path | None = None) -> list[Case]:
    """Read cases from YAML. Raise ValueError when a case is incomplete."""
    source = path or CASES_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{source} must be a non-empty list of cases.")
    cases: list[Case] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each case must be a mapping.")
        case = _case(item)
        if case.id in seen:
            raise ValueError(f"Duplicate case id {case.id}.")
        seen.add(case.id)
        cases.append(case)
    return cases


def _case(item: dict) -> Case:
    case_id = _text(item, "id")
    question = _text(item, "question")
    unanswerable = bool(item.get("unanswerable", False))
    facts = item.get("key_facts") or []
    if not isinstance(facts, list) or not all(isinstance(fact, str) and fact.strip() for fact in facts):
        if not unanswerable:
            raise ValueError(f"{case_id} needs a list of key_facts.")
        facts = []
    document = item.get("expected_document")
    chunk = item.get("expected_chunk")
    if unanswerable:
        return Case(case_id, question, None, None, tuple(facts), True)
    if not isinstance(document, str) or not document.strip():
        raise ValueError(f"{case_id} needs expected_document.")
    if not isinstance(chunk, int) or isinstance(chunk, bool) or chunk < 0:
        raise ValueError(f"{case_id} needs expected_chunk.")
    if not facts:
        raise ValueError(f"{case_id} needs key_facts.")
    return Case(case_id, question, document, chunk, tuple(facts), False)


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Case is missing {key}.")
    return value.strip()
