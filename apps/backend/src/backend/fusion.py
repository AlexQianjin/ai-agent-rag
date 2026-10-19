"""Reciprocal rank fusion for hybrid retrieval.

Qdrant returns one ranked list from BGE-M3 and another from BM25. This is the
standard RRF score, `1 / (k + rank)`, with ranks starting at 1 and `k` of 60.
A chunk that appears near the top of both lists outranks a chunk that only one
list likes. Later copies of the same id in a single list are ignored.
"""

from __future__ import annotations


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse ranked id lists. Higher scores come first, then the id."""
    if k < 0:
        raise ValueError("k must be zero or greater")
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        rank = 0
        for item in ranking:
            if item in seen:
                continue
            seen.add(item)
            rank += 1
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
