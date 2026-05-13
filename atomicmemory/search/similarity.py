"""Cosine similarity + top-k helpers.

Port of `atomicmemory-sdk/src/search/similarity-calculator.ts`. Uses
numpy for the dot/norm math; correctly handles zero-vectors and length
mismatches.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        The cosine similarity in ``[-1, 1]``. Returns ``0.0`` when either
        vector has zero L2 norm (avoids NaN).

    Raises:
        ValueError: When ``a`` and ``b`` have different lengths.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} != {len(b)}")
    arr_a = np.asarray(a, dtype=np.float64)
    arr_b = np.asarray(b, dtype=np.float64)
    norm_a = float(np.linalg.norm(arr_a))
    norm_b = float(np.linalg.norm(arr_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))


def batch_cosine_similarity(
    query: Sequence[float],
    candidates: Sequence[Sequence[float]],
) -> list[float]:
    """Compute cosine similarity between ``query`` and every candidate.

    Returns a list of similarities in candidate order; empty when
    ``candidates`` is empty.
    """
    if not candidates:
        return []
    q = np.asarray(query, dtype=np.float64)
    if q.size == 0:
        return [0.0] * len(candidates)
    matrix = np.asarray(candidates, dtype=np.float64)
    if matrix.shape[1] != q.shape[0]:
        raise ValueError(f"Query length {q.shape[0]} does not match candidate width {matrix.shape[1]}")
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0.0:
        return [0.0] * len(candidates)
    candidate_norms = np.linalg.norm(matrix, axis=1)
    dots = matrix @ q
    out: list[float] = []
    for value, norm in zip(dots, candidate_norms, strict=True):
        if norm == 0.0:
            out.append(0.0)
        else:
            out.append(float(value / (norm * q_norm)))
    return out


def rank_by_similarity(
    similarities: Sequence[float],
    *,
    threshold: float | None = None,
) -> list[int]:
    """Return candidate indices sorted by similarity descending.

    Optional ``threshold`` filters out indices whose similarity is
    strictly less than the threshold.
    """
    indices = list(range(len(similarities)))
    indices.sort(key=lambda i: similarities[i], reverse=True)
    if threshold is None:
        return indices
    return [i for i in indices if similarities[i] >= threshold]


def find_top_k(
    query_embedding: Sequence[float],
    candidates: Sequence[Sequence[float]],
    k: int,
    *,
    metadata: Sequence[Any] | None = None,
    threshold: float | None = None,
) -> list[tuple[int, float, Any]]:
    """Return up to ``k`` candidates as ``(index, similarity, metadata?)`` tuples.

    Sorted by similarity descending. ``metadata`` (when supplied) is
    aligned by index with ``candidates``.
    """
    if k <= 0:
        return []
    similarities = batch_cosine_similarity(query_embedding, candidates)
    ranked = rank_by_similarity(similarities, threshold=threshold)[:k]
    if metadata is None:
        return [(i, similarities[i], None) for i in ranked]
    if len(metadata) != len(candidates):
        raise ValueError(f"metadata length {len(metadata)} does not match candidates length {len(candidates)}")
    return [(i, similarities[i], metadata[i]) for i in ranked]
