"""Reciprocal rank fusion."""

from backend.fusion import reciprocal_rank_fusion


def test_overlap_outranks_a_single_list() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "d"]])
    assert [item for item, _score in fused] == ["b", "c", "a", "d"]
    scores = dict(fused)
    assert scores["b"] == 1 / 62 + 1 / 61
    assert scores["a"] == 1 / 61


def test_duplicate_in_one_list_keeps_the_better_rank() -> None:
    fused = reciprocal_rank_fusion([["a", "a", "b"]])
    assert [item for item, _score in fused] == ["a", "b"]
    assert dict(fused)["a"] == 1 / 61


def test_empty_rankings() -> None:
    assert reciprocal_rank_fusion([[], []]) == []
