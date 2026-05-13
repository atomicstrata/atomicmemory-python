"""Tests for similarity helpers."""

from __future__ import annotations

import math

import pytest

from atomicmemory.search.similarity import (
    batch_cosine_similarity,
    cosine_similarity,
    find_top_k,
    rank_by_similarity,
)


def test_cosine_identical_vectors_returns_one() -> None:
    assert math.isclose(cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)


def test_cosine_orthogonal_vectors_returns_zero() -> None:
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)


def test_cosine_zero_vector_returns_zero_no_nan() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0])


def test_batch_returns_per_candidate_score() -> None:
    sims = batch_cosine_similarity([1.0, 0.0], [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    assert math.isclose(sims[0], 1.0)
    assert math.isclose(sims[1], 0.0)


def test_rank_descending_with_threshold() -> None:
    ranked = rank_by_similarity([0.1, 0.9, 0.5, 0.05], threshold=0.2)
    assert ranked == [1, 2]


def test_find_top_k_returns_metadata_aligned() -> None:
    top = find_top_k(
        [1.0, 0.0],
        [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        2,
        metadata=["a", "b", "c"],
    )
    assert [t[0] for t in top] == [0, 2]
    assert top[0][2] == "a"
