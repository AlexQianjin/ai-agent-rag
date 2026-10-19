"""Retrieval and answer metrics.

Retrieval uses one relevant chunk per answerable question. Hit rate and
recall@k are the same in that case: 1 when that chunk is in the top k.
MRR is 1/rank, or 0 when the chunk is missing. nDCG@k uses binary relevance,
so a hit at rank r scores 1/log2(r+1).
"""

from __future__ import annotations

import math
from typing import Any


def rank_of(hits: list[tuple[str, int]], document: str, chunk: int) -> int | None:
    """1-based rank of a document chunk, or None when it is absent."""
    for index, (name, chunk_index) in enumerate(hits, start=1):
        if name == document and chunk_index == chunk:
            return index
    return None


def hit(rank: int | None, k: int) -> float:
    return 1.0 if rank is not None and rank <= k else 0.0


def recall_at_k(rank: int | None, k: int) -> float:
    """Fraction of the relevant chunks found in the top k. There is one."""
    return hit(rank, k)


def reciprocal_rank(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return 1.0 / rank


def ndcg_at_k(rank: int | None, k: int) -> float:
    """Binary nDCG@k. The ideal ranking puts the one relevant chunk first."""
    if rank is None or rank > k:
        return 0.0
    dcg = 1.0 / math.log2(rank + 1)
    ideal = 1.0 / math.log2(2)
    return dcg / ideal


def aggregate(ranks: list[int | None], k: int) -> dict[str, float]:
    """Mean hit rate, recall@k, MRR, and nDCG@k. `count` is the number of ranks."""
    count = len(ranks)
    if count == 0:
        return {"hit_rate": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "count": 0}
    return {
        "hit_rate": sum(hit(rank, k) for rank in ranks) / count,
        "recall_at_k": sum(recall_at_k(rank, k) for rank in ranks) / count,
        "mrr": sum(reciprocal_rank(rank) for rank in ranks) / count,
        "ndcg_at_k": sum(ndcg_at_k(rank, k) for rank in ranks) / count,
        "count": count,
    }


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def threshold_failures(metrics: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    """Names of metrics that sit under the configured floors.

    Dense and BM25 are reported and are not gated. Answer floors apply only
    when the run judged answers.
    """
    failures: list[str] = []
    hybrid = metrics.get("hybrid") or {}
    for key, minimum in (thresholds.get("retrieval") or {}).get("hybrid", {}).items():
        actual = hybrid.get(key)
        if actual is None:
            failures.append(f"hybrid {key} is missing")
            continue
        if float(actual) + 1e-9 < float(minimum):
            failures.append(f"hybrid {key} {float(actual):.3f} is below {float(minimum):.3f}")
    answer_floors = thresholds.get("answer") or {}
    answer = metrics.get("answer")
    if answer is None or answer.get("faithfulness") is None:
        return failures
    for key, minimum in answer_floors.items():
        actual = answer.get(key)
        if actual is None:
            failures.append(f"answer {key} is missing")
            continue
        if float(actual) + 1e-9 < float(minimum):
            failures.append(f"answer {key} {float(actual):.3f} is below {float(minimum):.3f}")
    return failures


def case_failure_reasons(row: dict[str, Any], thresholds: dict[str, Any], k: int) -> list[str]:
    """Why one question missed, for the report. Empty when it looks fine."""
    reasons: list[str] = []
    answer_floors = thresholds.get("answer") or {}
    if row.get("unanswerable"):
        if row.get("refusal_correct") is False:
            reasons.append("the answer should have refused, and the judge disagreed")
        return reasons
    if row.get("hybrid_hit") is False:
        reasons.append(
            f"hybrid missed {row.get('expected_document')} chunk {row.get('expected_chunk')} in top {k}"
        )
    if row.get("citation_correct") is False:
        reasons.append("the cited document and chunk do not match the expected source")
    faithfulness = row.get("faithfulness")
    floor = answer_floors.get("faithfulness")
    if faithfulness is not None and floor is not None and float(faithfulness) + 1e-9 < float(floor):
        reasons.append(f"faithfulness {float(faithfulness):.3f} is below {float(floor):.3f}")
    relevance = row.get("relevance")
    floor = answer_floors.get("relevance")
    if relevance is not None and floor is not None and float(relevance) + 1e-9 < float(floor):
        reasons.append(f"relevance {float(relevance):.3f} is below {float(floor):.3f}")
    return reasons
