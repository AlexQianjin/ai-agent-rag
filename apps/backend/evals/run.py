"""Run the golden-set evaluation.

    uv run python -m evals.run --retrieval-only
    uv run python -m evals.run
    uv run python -m evals.run --check evals/reports/example.json

Retrieval compares dense-only, BM25-only, and hybrid reciprocal rank fusion.
The full run also answers with the LangGraph agent and scores the answer with
an LLM judge. Thresholds live in `thresholds.yaml`. A miss exits 1.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from evals.answer import judge_turn, run_turn
from evals.dataset import ROOT, Case, load_cases
from evals.judge import load_criteria
from evals.metrics import aggregate, case_failure_reasons, mean, rank_of, threshold_failures
from evals.report import print_summary, write_reports
from evals.retrieval import (
    EvalError,
    answerable,
    index_documents,
    labeled_hits,
    names_by_id,
    search_hits,
)

THRESHOLDS_PATH = ROOT / "thresholds.yaml"
REPORTS_DIR = ROOT / "reports"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    parser.add_argument("--retrieval-only", action="store_true", help="Skip the agent and the judge.")
    parser.add_argument("--cases", type=Path, default=None, help="YAML file of questions.")
    parser.add_argument("--reports", type=Path, default=REPORTS_DIR, help="Directory for JSON and Markdown.")
    parser.add_argument("--thresholds", type=Path, default=THRESHOLDS_PATH)
    parser.add_argument("--k", type=int, default=None, help="Override the cutoff in the thresholds file.")
    parser.add_argument("--check", type=Path, default=None, help="Re-check a saved JSON report and exit.")
    args = parser.parse_args(argv)
    try:
        thresholds = load_thresholds(args.thresholds)
        if args.k is not None:
            if args.k < 1:
                raise EvalError("--k must be positive.")
            thresholds = {**thresholds, "k": args.k}
        if args.check is not None:
            report = json.loads(args.check.read_text(encoding="utf-8"))
            return _gate(report, thresholds)
        return _run(args, thresholds)
    except (EvalError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def load_thresholds(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EvalError(f"{path} must be a mapping.")
    if not isinstance(data.get("k"), int) or data["k"] < 1:
        raise EvalError(f"{path} needs a positive integer k.")
    return data


def _run(args: argparse.Namespace, thresholds: dict[str, Any]) -> int:
    from evals.config import EvalSettings

    settings = EvalSettings.from_env()
    if not args.retrieval_only and not settings.api_key.strip():
        raise EvalError("XAI_API_KEY is not set. Pass --retrieval-only, or set the key.")
    cases = load_cases(args.cases)
    k = int(thresholds["k"])
    from backend.embeddings import EmbeddingClient
    from backend.vector_store import VectorStore

    embedder = EmbeddingClient(
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout=settings.embedding_timeout,
    )
    store = VectorStore(
        url=settings.qdrant_url,
        collection=settings.collection,
        dimension=settings.embedding_dimension,
    )
    print(f"collection {settings.collection} at {settings.qdrant_url}")
    documents = index_documents(store, embedder)
    names = names_by_id(documents)
    rows = _score_retrieval(cases, store, embedder, names, k)
    judged = False
    if not args.retrieval_only:
        criteria = load_criteria()
        _score_answers(rows, cases, store, embedder, names, k, settings, criteria)
        judged = True
    report = _report(rows, cases, k, thresholds, judged=judged)
    json_path, markdown_path = write_reports(report, args.reports)
    print_summary(report)
    print(f"\nWrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0 if report["passed"] else 1


def _score_retrieval(cases, store, embedder, names, k: int) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for case in cases:
        row = _blank_row(case)
        if not case.unanswerable:
            started = time.perf_counter()
            vector = embedder.embed([case.question])[0]
            for mode in ("dense", "bm25", "hybrid"):
                hits = search_hits(store, mode=mode, query=case.question, vector=vector, top_k=k)
                labeled = labeled_hits(hits, names)
                document, chunk = expected_label(case)
                rank = rank_of(labeled, document, chunk)
                row[f"{mode}_rank"] = rank
                row[f"{mode}_hit"] = rank is not None and rank <= k
            row["retrieval_latency_ms"] = (time.perf_counter() - started) * 1000
        rows[case.id] = row
        print(f"scored {case.id}")
    return rows


def _score_answers(rows, cases, store, embedder, names, k, settings, criteria: str) -> None:
    for case in cases:
        turn = run_turn(
            case,
            store=store,
            embedder=embedder,
            names=names,
            top_k=k,
            base_url=settings.llm_base_url,
            api_key=settings.api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
        judged = judge_turn(
            case,
            turn["answer"],
            turn["sources"],
            base_url=settings.judge_base_url,
            api_key=settings.api_key,
            model=settings.judge_model,
            timeout=settings.llm_timeout,
            criteria=criteria,
        )
        row = rows[case.id]
        row["answer"] = turn["answer"]
        row["citation_correct"] = turn["citation_correct"]
        row["answer_latency_ms"] = turn["answer_latency_ms"]
        row["answer_tokens"] = turn["answer_tokens"]
        row.update(judged)
        print(f"judged {case.id}")


def _report(
    rows: dict[str, dict[str, Any]],
    cases: list[Case],
    k: int,
    thresholds: dict[str, Any],
    *,
    judged: bool,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    kept = answerable(cases)
    metrics: dict[str, Any] = {}
    for mode in ("dense", "bm25", "hybrid"):
        ranks = [rows[case.id][f"{mode}_rank"] for case in kept]
        metrics[mode] = aggregate(ranks, k)
    answer_metrics = _answer_metrics(rows, cases) if judged else _empty_answer()
    metrics["answer"] = answer_metrics
    ordered = []
    for case in cases:
        row = rows[case.id]
        active = thresholds if judged else {"answer": {}}
        row["failure_reasons"] = case_failure_reasons(row, active, k)
        ordered.append(row)
    report = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "full" if judged else "retrieval",
        "k": k,
        "answerable_count": len(kept),
        "unanswerable_count": len(cases) - len(kept),
        "metrics": metrics,
        "thresholds": thresholds,
        "threshold_failures": [],
        "passed": True,
        "cases": ordered,
    }
    failures = threshold_failures(metrics, thresholds if judged else _retrieval_only_thresholds(thresholds))
    report["threshold_failures"] = failures
    report["passed"] = not failures
    return report


def _answer_metrics(rows: dict[str, dict[str, Any]], cases: list[Case]) -> dict[str, Any]:
    answerable_cases = [case for case in cases if not case.unanswerable]
    unanswerable_cases = [case for case in cases if case.unanswerable]
    faithfulness = [float(rows[case.id]["faithfulness"]) for case in cases]
    relevance = [float(rows[case.id]["relevance"]) for case in cases]
    citations = [1.0 if rows[case.id]["citation_correct"] else 0.0 for case in answerable_cases]
    refusals = [1.0 if rows[case.id]["refusal_correct"] else 0.0 for case in unanswerable_cases]
    answer_latency = [float(rows[case.id]["answer_latency_ms"]) for case in cases]
    judge_latency = [float(rows[case.id]["judge_latency_ms"]) for case in cases]
    return {
        "faithfulness": mean(faithfulness),
        "relevance": mean(relevance),
        "citation_accuracy": mean(citations),
        "refusal_correctness": mean(refusals),
        "mean_answer_latency_ms": mean(answer_latency),
        "mean_judge_latency_ms": mean(judge_latency),
        "answer_prompt_tokens": _sum_tokens(rows, cases, "answer_tokens", "prompt_tokens"),
        "answer_completion_tokens": _sum_tokens(rows, cases, "answer_tokens", "completion_tokens"),
        "judge_prompt_tokens": _sum_tokens(rows, cases, "judge_tokens", "prompt_tokens"),
        "judge_completion_tokens": _sum_tokens(rows, cases, "judge_tokens", "completion_tokens"),
    }


def _empty_answer() -> dict[str, Any]:
    return {
        "faithfulness": None,
        "relevance": None,
        "citation_accuracy": None,
        "refusal_correctness": None,
        "mean_answer_latency_ms": None,
        "mean_judge_latency_ms": None,
        "answer_prompt_tokens": None,
        "answer_completion_tokens": None,
        "judge_prompt_tokens": None,
        "judge_completion_tokens": None,
    }


def _sum_tokens(rows: dict[str, dict[str, Any]], cases: list[Case], field: str, key: str) -> int | None:
    total = 0
    seen = False
    for case in cases:
        usage = rows[case.id].get(field) or {}
        value = usage.get(key)
        if value is None:
            continue
        seen = True
        total += int(value)
    return total if seen else None


def _retrieval_only_thresholds(thresholds: dict[str, Any]) -> dict[str, Any]:
    return {"k": thresholds["k"], "retrieval": thresholds.get("retrieval") or {}}


def _gate(report: dict[str, Any], thresholds: dict[str, Any]) -> int:
    judged = (report.get("metrics") or {}).get("answer", {}).get("faithfulness") is not None
    active = thresholds if judged else _retrieval_only_thresholds(thresholds)
    failures = threshold_failures(report.get("metrics") or {}, active)
    report = {**report, "threshold_failures": failures, "passed": not failures}
    print_summary(report)
    return 0 if report["passed"] else 1


def expected_label(case: Case) -> tuple[str, int]:
    """Document name and chunk. Chunk 0 is a real label, not a missing value."""
    if case.expected_chunk is None:
        return case.expected_document or "", -1
    return case.expected_document or "", case.expected_chunk


def _blank_row(case: Case) -> dict[str, Any]:
    return {
        "id": case.id,
        "question": case.question,
        "unanswerable": case.unanswerable,
        "expected_document": case.expected_document,
        "expected_chunk": case.expected_chunk,
        "key_facts": list(case.key_facts),
        "dense_rank": None,
        "bm25_rank": None,
        "hybrid_rank": None,
        "dense_hit": None,
        "bm25_hit": None,
        "hybrid_hit": None,
        "retrieval_latency_ms": None,
        "answer": None,
        "citation_correct": None,
        "faithfulness": None,
        "relevance": None,
        "refused": None,
        "refusal_correct": None,
        "notes": None,
        "answer_latency_ms": None,
        "judge_latency_ms": None,
        "answer_tokens": None,
        "judge_tokens": None,
        "failure_reasons": [],
    }


if __name__ == "__main__":
    raise SystemExit(main())
