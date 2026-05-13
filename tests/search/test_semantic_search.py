"""Tests for SemanticSearch orchestrator + ranking."""

from __future__ import annotations

from atomicmemory.search.ranking import RankableHit, RankingConfig, rerank
from atomicmemory.search.semantic_search import (
    SemanticSearch,
    SemanticSearchConfig,
    StoredContext,
)


def _embed(text: str) -> list[float]:
    """Toy embedding: word counts on fixed vocabulary."""
    vocab = ["alpha", "beta", "gamma"]
    return [text.lower().count(w) for w in vocab]


def _ctx(id_: str, content: str, *, timestamp: float | None = None, user: str | None = None) -> StoredContext:
    return StoredContext(
        id=id_,
        content=content,
        embedding=_embed(content),
        timestamp=timestamp,
        user_id=user,
    )


def test_semantic_search_returns_top_k() -> None:
    search = SemanticSearch(embed_fn=_embed, config=SemanticSearchConfig(reranking_enabled=False))
    contexts = [_ctx("a", "alpha"), _ctx("b", "beta"), _ctx("c", "gamma")]
    results = search.search("alpha", contexts, top_k=1)
    assert len(results) == 1
    assert results[0].context.id == "a"


def test_search_with_threshold_filters_low_similarity() -> None:
    search = SemanticSearch(embed_fn=_embed, config=SemanticSearchConfig(reranking_enabled=False))
    contexts = [_ctx("a", "alpha"), _ctx("b", "beta")]
    results = search.search("alpha", contexts, threshold=0.99)
    assert [r.context.id for r in results] == ["a"]


def test_search_with_filter_fn() -> None:
    search = SemanticSearch(embed_fn=_embed, config=SemanticSearchConfig(reranking_enabled=False))
    contexts = [_ctx("a", "alpha", user="u1"), _ctx("b", "alpha", user="u2")]
    results = search.search("alpha", contexts, filter_fn=lambda c: c.user_id == "u1")
    assert [r.context.id for r in results] == ["a"]


def test_rerank_short_content_boosts_score() -> None:
    hits = [RankableHit(content="short", score=0.5), RankableHit(content="x" * 3000, score=0.5)]
    adjusted = rerank(hits, config=RankingConfig())
    short = next(h for h in adjusted if h.content == "short")
    long = next(h for h in adjusted if h.content == "x" * 3000)
    assert short.score > long.score


def test_rerank_caps_at_score_cap() -> None:
    hits = [RankableHit(content="short", score=0.95)]
    adjusted = rerank(hits, config=RankingConfig(score_cap=1.0, short_boost=2.0))
    assert adjusted[0].score == 1.0


def test_search_returns_empty_for_empty_input() -> None:
    search = SemanticSearch(embed_fn=_embed)
    assert search.search("alpha", []) == []


def test_rerank_path_preserves_all_results_with_duplicate_content() -> None:
    """Regression: previous match-back keyed on (content, score) and dropped
    one of the two duplicates because rerank also mutates the score."""
    search = SemanticSearch(embed_fn=_embed, config=SemanticSearchConfig(reranking_enabled=True))
    contexts = [_ctx("a", "alpha"), _ctx("b", "alpha")]
    results = search.search("alpha", contexts, top_k=2)
    assert len(results) == 2
    assert {r.context.id for r in results} == {"a", "b"}


def test_rerank_path_preserves_all_results_with_identical_scores() -> None:
    """Two distinct contexts, both perfectly matching the query → tied scores."""
    search = SemanticSearch(embed_fn=_embed, config=SemanticSearchConfig(reranking_enabled=True))
    contexts = [_ctx("a", "alpha alpha"), _ctx("b", "alpha alpha")]
    results = search.search("alpha alpha", contexts, top_k=2)
    assert len(results) == 2
    assert {r.context.id for r in results} == {"a", "b"}
