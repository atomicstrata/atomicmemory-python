"""End-to-end tests for AtomicMemoryProvider against a mocked core HTTP API."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from atomicmemory.memory.types import (
    ListRequest,
    MemoryRef,
    PackageRequest,
    Scope,
    SearchRequest,
    TextIngest,
    VerbatimIngest,
)
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


@pytest.fixture
def provider() -> AtomicMemoryProvider:
    cfg = AtomicMemoryProviderConfig(api_url="http://core.test", api_version="v1")
    p = AtomicMemoryProvider(cfg)
    p.initialize()
    yield p
    p.close()


@respx.mock
def test_ingest_text_posts_extraction_path(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/ingest").mock(
        return_value=httpx.Response(
            200,
            json={
                "episode_id": "ep-1",
                "facts_extracted": 1,
                "memories_stored": 1,
                "memories_updated": 0,
                "memories_deleted": 0,
                "memories_skipped": 0,
                "stored_memory_ids": ["m-1"],
                "updated_memory_ids": [],
                "links_created": 0,
                "composites_created": 0,
            },
        )
    )
    result = provider.ingest(TextIngest(content="I prefer aisles", scope=Scope(user="u1")))

    assert result.created == ["m-1"]
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "user_id": "u1",
        "conversation": "I prefer aisles",
        "source_site": "sdk",
        "source_url": "",
    }


@respx.mock
def test_ingest_verbatim_posts_quick_path_with_skip_extraction(
    provider: AtomicMemoryProvider,
) -> None:
    route = respx.post("http://core.test/v1/memories/ingest/quick").mock(
        return_value=httpx.Response(
            200,
            json={
                "episode_id": "ep-1",
                "facts_extracted": 0,
                "memories_stored": 1,
                "memories_updated": 0,
                "memories_deleted": 0,
                "memories_skipped": 0,
                "stored_memory_ids": ["m-1"],
                "updated_memory_ids": [],
                "links_created": 0,
                "composites_created": 0,
            },
        )
    )

    provider.ingest(VerbatimIngest(content="raw note", scope=Scope(user="u1"), metadata={"k": "v"}))

    body = json.loads(route.calls[0].request.content)
    assert body["skip_extraction"] is True
    assert body["metadata"] == {"k": "v"}


@respx.mock
def test_search_posts_fast_path_and_maps_scores(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [
                    {
                        "id": "m-1",
                        "content": "aisles",
                        "semantic_similarity": 0.91,
                        "ranking_score": 0.88,
                        "relevance": 0.75,
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "count": 1,
            },
        )
    )

    page = provider.search(SearchRequest(query="seat preference", scope=Scope(user="u1")))

    assert len(page.results) == 1
    hit = page.results[0]
    assert hit.memory.id == "m-1"
    assert hit.similarity == 0.91
    assert hit.ranking_score == 0.88
    assert hit.relevance == 0.75


@respx.mock
def test_get_returns_none_on_404(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/m-x").mock(return_value=httpx.Response(404))
    assert provider.get(MemoryRef(id="m-x", scope=Scope(user="u1"))) is None


@respx.mock
def test_delete_swallows_404(provider: AtomicMemoryProvider) -> None:
    respx.delete("http://core.test/v1/memories/m-x").mock(return_value=httpx.Response(404))
    provider.delete(MemoryRef(id="m-x", scope=Scope(user="u1")))


@respx.mock
def test_list_paginates_with_cursor(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/list").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [
                    {"id": "m-1", "content": "a", "created_at": "2024-01-01T00:00:00Z"},
                    {"id": "m-2", "content": "b", "created_at": "2024-01-02T00:00:00Z"},
                ],
                "count": 2,
            },
        )
    )

    page = provider.list(ListRequest(scope=Scope(user="u1"), limit=2))

    assert [m.id for m in page.memories] == ["m-1", "m-2"]
    assert page.cursor == "2"


@respx.mock
def test_search_as_of_serializes_iso_datetime(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(200, json={"memories": []}),
    )
    when = datetime(2024, 6, 1, tzinfo=timezone.utc)

    provider.search_as_of(SearchRequest(query="q", scope=Scope(user="u1")), when)

    body = json.loads(route.calls[0].request.content)
    assert body["as_of"] == "2024-06-01T00:00:00+00:00"


@respx.mock
def test_package_returns_text_and_tokens(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [
                    {"id": "m-1", "content": "hi", "ranking_score": 0.5, "created_at": "2024-01-01T00:00:00Z"},
                ],
                "injection_text": "hi\n",
                "estimated_context_tokens": 7,
                "budget_constrained": False,
            },
        )
    )
    pkg = provider.package(
        PackageRequest(query="q", scope=Scope(user="u1"), token_budget=128, format="tiered"),
    )

    assert pkg.text == "hi\n"
    assert pkg.tokens == 7
    assert len(pkg.results) == 1
    assert pkg.budget_constrained is False


@respx.mock
def test_package_propagates_budget_constrained_true(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [],
                "injection_text": "",
                "estimated_context_tokens": 0,
                "budget_constrained": True,
            },
        )
    )
    pkg = provider.package(PackageRequest(query="q", scope=Scope(user="u1"), token_budget=5))
    assert pkg.budget_constrained is True


@respx.mock
def test_package_raises_when_budget_constrained_missing(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={"memories": [], "injection_text": "", "estimated_context_tokens": 0},
        )
    )
    with pytest.raises(ValueError, match="budget_constrained"):
        provider.package(PackageRequest(query="q", scope=Scope(user="u1")))


@respx.mock
def test_package_raises_when_budget_constrained_not_boolean(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [],
                "injection_text": "",
                "estimated_context_tokens": 0,
                "budget_constrained": "yes",
            },
        )
    )
    with pytest.raises(ValueError, match="budget_constrained"):
        provider.package(PackageRequest(query="q", scope=Scope(user="u1")))


@respx.mock
def test_health_returns_ok_flag(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )

    assert provider.health().ok is True


def test_capabilities_advertises_atomicmemory_namespace(
    provider: AtomicMemoryProvider,
) -> None:
    """Every advertised custom_extension must resolve via get_extension."""
    caps = provider.capabilities()

    assert caps.custom_extensions is not None
    for name in (
        "atomicmemory.base",
        "atomicmemory.lifecycle",
        "atomicmemory.audit",
        "atomicmemory.lessons",
        "atomicmemory.config",
        "atomicmemory.agents",
    ):
        assert name in caps.custom_extensions
        assert provider.get_extension(name) is not None
