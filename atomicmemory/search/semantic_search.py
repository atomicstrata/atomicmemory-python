"""Local SemanticSearch orchestrator — embed → score → rank.

Port of `atomicmemory-sdk/src/search/semantic-search.ts`. Brute-force
linear scan against an in-memory list of :class:`StoredContext`. No
HNSW / IVF — designed for small-to-medium local stores (<10k items)
where simplicity beats indexing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atomicmemory.search.ranking import RankableHit, RankingConfig, rerank
from atomicmemory.search.similarity import batch_cosine_similarity, rank_by_similarity

EmbedFn = Callable[[str], list[float]]
"""Callable that turns a query string into an embedding vector."""


@dataclass(frozen=True)
class StoredContext:
    """A single context record indexed for local search."""

    id: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] | None = None
    timestamp: float | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class SemanticSearchResult:
    context: StoredContext
    score: float


@dataclass(frozen=True)
class SemanticSearchConfig:
    """Search-time knobs."""

    default_top_k: int = 10
    default_threshold: float = 0.1
    max_results: int = 100
    reranking_enabled: bool = True
    ranking: RankingConfig = field(default_factory=RankingConfig)


class SemanticSearch:
    """Brute-force semantic search over an in-memory context list."""

    def __init__(
        self,
        embed_fn: EmbedFn,
        *,
        config: SemanticSearchConfig | None = None,
    ) -> None:
        self._embed = embed_fn
        self._config = config or SemanticSearchConfig()

    @property
    def config(self) -> SemanticSearchConfig:
        return self._config

    def search(
        self,
        query: str,
        contexts: Sequence[StoredContext],
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        filter_fn: Callable[[StoredContext], bool] | None = None,
        rerank_results: bool | None = None,
    ) -> list[SemanticSearchResult]:
        """Return up to ``top_k`` matches, optionally reranked.

        Args:
            query: Free-text query.
            contexts: Candidate pool to score.
            top_k: Cap on returned results. Defaults to
                ``config.default_top_k``; clamped to ``config.max_results``.
            threshold: Minimum cosine similarity. Defaults to
                ``config.default_threshold``.
            filter_fn: Optional predicate run before scoring (cheap pre-
                filter, e.g. by user_id).
            rerank_results: Override config's ``reranking_enabled``.
        """
        if not contexts:
            return []
        candidates = [ctx for ctx in contexts if filter_fn(ctx)] if filter_fn is not None else list(contexts)
        if not candidates:
            return []
        query_embedding = self._embed(query)
        similarities = batch_cosine_similarity(query_embedding, [ctx.embedding for ctx in candidates])
        effective_threshold = threshold if threshold is not None else self._config.default_threshold
        ranked_indices = rank_by_similarity(similarities, threshold=effective_threshold)
        effective_top_k = min(
            top_k if top_k is not None else self._config.default_top_k,
            self._config.max_results,
        )
        ranked_indices = ranked_indices[:effective_top_k]
        primary = [SemanticSearchResult(context=candidates[i], score=similarities[i]) for i in ranked_indices]
        do_rerank = rerank_results if rerank_results is not None else self._config.reranking_enabled
        if not do_rerank or not primary:
            return primary
        return self._apply_rerank(primary)

    def _apply_rerank(self, results: list[SemanticSearchResult]) -> list[SemanticSearchResult]:
        # Tag each rankable with its original-index so the reranked
        # output maps back unambiguously even when scores or content
        # collide.
        rankable = [
            RankableHit(
                content=r.context.content,
                score=r.score,
                timestamp_seconds=r.context.timestamp,
                original_index=i,
            )
            for i, r in enumerate(results)
        ]
        adjusted = rerank(rankable, config=self._config.ranking, now=datetime.now(tz=timezone.utc))
        reordered: list[SemanticSearchResult] = []
        for hit in adjusted:
            if hit.original_index is None:
                continue
            reordered.append(SemanticSearchResult(context=results[hit.original_index].context, score=hit.score))
        return reordered
