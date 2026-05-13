"""Heuristic reranking for local semantic search results.

Port of the rerank heuristics in
`atomicmemory-sdk/src/search/semantic-search.ts:rerankResults`.
Three signals: short-content boost, long-content penalty, recency
boost. Pure functions; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RankingConfig:
    """Tunable reranking knobs."""

    short_threshold: int = 500
    short_boost: float = 1.1
    long_threshold: int = 2000
    long_penalty: float = 0.9
    recency_window_days: int = 7
    recency_boost: float = 1.05
    score_cap: float = 1.0


@dataclass
class RankableHit:
    """Minimal shape rerank operates on; field names match the TS port.

    ``original_index`` lets callers map the reranked output back to their
    own list without relying on content/score equality (rerank mutates
    score, and content can collide between hits).
    """

    content: str
    score: float
    timestamp_seconds: float | None = None
    original_index: int | None = None


def _length_factor(content: str, config: RankingConfig) -> float:
    length = len(content)
    if length < config.short_threshold:
        return config.short_boost
    if length > config.long_threshold:
        return config.long_penalty
    return 1.0


def _recency_factor(timestamp_seconds: float | None, *, now: datetime, config: RankingConfig) -> float:
    if timestamp_seconds is None:
        return 1.0
    delta = now.timestamp() - timestamp_seconds
    window_seconds = config.recency_window_days * 24 * 60 * 60
    if delta < window_seconds:
        return config.recency_boost
    return 1.0


def rerank(
    hits: list[RankableHit],
    *,
    config: RankingConfig | None = None,
    now: datetime | None = None,
) -> list[RankableHit]:
    """Apply length + recency heuristics; sort by adjusted score descending.

    Args:
        hits: Hits to rerank. Mutated in place is **not** allowed — a new
            list is returned.
        config: Tunable thresholds; defaults to :class:`RankingConfig`.
        now: Reference time for recency. Defaults to UTC now.

    Returns:
        New list of hits with adjusted ``score`` values, sorted descending.
    """
    cfg = config or RankingConfig()
    reference = now or datetime.now(tz=timezone.utc)
    adjusted: list[RankableHit] = []
    for hit in hits:
        factor = _length_factor(hit.content, cfg) * _recency_factor(hit.timestamp_seconds, now=reference, config=cfg)
        new_score = min(hit.score * factor, cfg.score_cap)
        adjusted.append(
            RankableHit(
                content=hit.content,
                score=new_score,
                timestamp_seconds=hit.timestamp_seconds,
                original_index=hit.original_index,
            )
        )
    adjusted.sort(key=lambda h: h.score, reverse=True)
    return adjusted
