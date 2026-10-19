"""Metric math, the golden set, and the threshold exit."""

import json
from pathlib import Path

from evals.answer import citation_correct
from evals.dataset import DOCUMENTS_DIR, Case, load_cases
from evals.judge import parse_judge
from evals.metrics import aggregate, hit, ndcg_at_k, rank_of, recall_at_k, reciprocal_rank, threshold_failures
from evals.run import expected_label, main

_HITS = [("orchard.txt", 0), ("harbor.txt", 1), ("workshop.docx", 2)]


def test_chunk_zero_stays_the_expected_label() -> None:
    case = Case("apple-variety", "What variety is the crimson apple?", "orchard.txt", 0, ("Lumen",), False)
    assert expected_label(case) == ("orchard.txt", 0)
    assert rank_of([("orchard.txt", 0)], "orchard.txt", 0) == 1


def test_rank_hit_recall_mrr_and_ndcg() -> None:
    assert rank_of(_HITS, "harbor.txt", 1) == 2
    assert rank_of(_HITS, "orchard.txt", 3) is None
    assert hit(1, 5) == 1
    assert hit(6, 5) == 0
    assert hit(None, 5) == 0
    assert recall_at_k(2, 5) == 1
    assert recall_at_k(None, 5) == 0
    assert reciprocal_rank(2) == 0.5
    assert reciprocal_rank(None) == 0
    assert ndcg_at_k(1, 5) == 1
    assert ndcg_at_k(2, 5) < 1
    assert ndcg_at_k(6, 5) == 0


def test_aggregate_means_one_relevant_chunk() -> None:
    summary = aggregate([1, None], k=5)
    assert summary["count"] == 2
    assert summary["hit_rate"] == 0.5
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.5
    assert summary["ndcg_at_k"] == 0.5


def test_threshold_failure_names_the_metric() -> None:
    metrics = {
        "hybrid": {"hit_rate": 0.4, "recall_at_k": 0.9, "mrr": 0.9, "ndcg_at_k": 0.9},
        "answer": {"faithfulness": None},
    }
    thresholds = {"retrieval": {"hybrid": {"hit_rate": 0.75, "recall_at_k": 0.75}}}
    failures = threshold_failures(metrics, thresholds)
    assert len(failures) == 1
    assert "hit_rate" in failures[0]


def test_check_command_exits_nonzero_when_hybrid_is_under_the_floor(tmp_path: Path) -> None:
    report = {
        "k": 5,
        "answerable_count": 2,
        "unanswerable_count": 0,
        "mode": "retrieval",
        "metrics": {
            "dense": {"hit_rate": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0},
            "bm25": {"hit_rate": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0},
            "hybrid": {"hit_rate": 0.2, "recall_at_k": 0.2, "mrr": 0.2, "ndcg_at_k": 0.2},
            "answer": {"faithfulness": None},
        },
        "cases": [],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    thresholds = tmp_path / "thresholds.yaml"
    thresholds.write_text(
        "k: 5\nretrieval:\n  hybrid:\n    hit_rate: 0.75\n    recall_at_k: 0.75\n    mrr: 0.6\n    ndcg_at_k: 0.65\n",
        encoding="utf-8",
    )
    assert main(["--check", str(path), "--thresholds", str(thresholds)]) == 1


def test_check_command_exits_zero_when_metrics_clear_the_floor(tmp_path: Path) -> None:
    report = {
        "k": 5,
        "answerable_count": 1,
        "unanswerable_count": 0,
        "mode": "retrieval",
        "metrics": {
            "dense": {"hit_rate": 1, "recall_at_k": 1, "mrr": 1, "ndcg_at_k": 1},
            "bm25": {"hit_rate": 1, "recall_at_k": 1, "mrr": 1, "ndcg_at_k": 1},
            "hybrid": {"hit_rate": 1, "recall_at_k": 1, "mrr": 1, "ndcg_at_k": 1},
            "answer": {"faithfulness": None},
        },
        "cases": [],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    thresholds = tmp_path / "thresholds.yaml"
    thresholds.write_text(
        "k: 5\nretrieval:\n  hybrid:\n    hit_rate: 0.75\nanswer:\n  faithfulness: 0.9\n",
        encoding="utf-8",
    )
    assert main(["--check", str(path), "--thresholds", str(thresholds)]) == 0


def test_golden_set_covers_documents_and_refusals() -> None:
    cases = load_cases()
    assert 20 <= len(cases) <= 30
    answerable = [case for case in cases if not case.unanswerable]
    refused = [case for case in cases if case.unanswerable]
    assert len(answerable) >= 12
    assert len(refused) >= 4
    names = {case.expected_document for case in answerable}
    assert names == {"orchard.txt", "harbor.txt", "workshop.docx", "field-notes.pdf"}
    for name in names:
        assert (DOCUMENTS_DIR / name).is_file()
    assert len({case.id for case in cases}) == len(cases)


def test_citation_matches_the_cited_source() -> None:
    sources = [
        {"document_name": "harbor.txt", "chunk_index": 1},
        {"document_name": "orchard.txt", "chunk_index": 0},
    ]
    assert citation_correct("The variety is Lumen [2].", sources, "orchard.txt", 0)
    assert not citation_correct("The variety is Lumen [1].", sources, "orchard.txt", 0)
    assert not citation_correct("The variety is Lumen.", sources, "orchard.txt", 0)


def test_judge_json_strips_a_fence() -> None:
    text = '```json\n{"faithfulness": 0.5, "relevance": 1, "refused": false, "notes": "ok"}\n```'
    faithfulness, relevance, refused, notes = parse_judge(text)
    assert faithfulness == 0.5
    assert relevance == 1
    assert refused is False
    assert notes == "ok"
