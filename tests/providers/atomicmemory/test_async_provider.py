"""Tests for AsyncAtomicMemoryProvider — async mirror of provider tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
import respx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.types import (
    ListRequest,
    MemoryRef,
    PackageRequest,
    Scope,
    SearchRequest,
    TextIngest,
)
from atomicmemory.providers.atomicmemory.async_handle_impl import AsyncAtomicMemoryHandle
from atomicmemory.providers.atomicmemory.async_provider import AsyncAtomicMemoryProvider
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig


@pytest_asyncio.fixture
async def provider() -> AsyncAtomicMemoryProvider:
    p = AsyncAtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    await p.initialize()
    yield p
    await p.close()


@pytest.mark.asyncio
@respx.mock
async def test_async_ingest_text(provider: AsyncAtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/ingest").mock(
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
    result = await provider.ingest(TextIngest(content="hi", scope=Scope(user="u1")))
    assert result.created == ["m-1"]


@pytest.mark.asyncio
@respx.mock
async def test_async_ingest_maps_thread_to_session_id(provider: AsyncAtomicMemoryProvider) -> None:
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

    await provider.ingest(TextIngest(content="hi", scope=Scope(user="u1", thread="thread-1")))

    body = json.loads(route.calls[0].request.content)
    assert body["session_id"] == "thread-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_search_returns_typed_page(
    provider: AsyncAtomicMemoryProvider,
) -> None:
    respx.post("http://core.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [
                    {
                        "id": "m-1",
                        "content": "x",
                        "ranking_score": 0.42,
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "count": 1,
            },
        )
    )
    page = await provider.search(SearchRequest(query="q", scope=Scope(user="u1")))
    assert page.results[0].score == 0.42


@pytest.mark.asyncio
@respx.mock
async def test_async_search_maps_thread_to_session_id(provider: AsyncAtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(200, json={"memories": [], "count": 0}),
    )

    await provider.search(SearchRequest(query="q", scope=Scope(user="u1", thread="thread-1")))

    body = json.loads(route.calls[0].request.content)
    assert body["session_id"] == "thread-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_search_rejects_thread_scoped_rows_without_session_id(
    provider: AsyncAtomicMemoryProvider,
) -> None:
    respx.post("http://core.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(200, json={"memories": [{"id": "m-1", "content": "x"}], "count": 1}),
    )

    with pytest.raises(ProviderError, match="session_id"):
        await provider.search(SearchRequest(query="q", scope=Scope(user="u1", thread="thread-1")))


@pytest.mark.asyncio
@respx.mock
async def test_async_get_returns_none_on_404(
    provider: AsyncAtomicMemoryProvider,
) -> None:
    respx.get(url__regex=r"http://core.test/v1/memories/m-x.*").mock(return_value=httpx.Response(404))
    assert await provider.get(MemoryRef(id="m-x", scope=Scope(user="u1"))) is None


@pytest.mark.asyncio
@respx.mock
async def test_async_list_paginates(provider: AsyncAtomicMemoryProvider) -> None:
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
    page = await provider.list(ListRequest(scope=Scope(user="u1"), limit=2))
    assert page.cursor == "2"


@pytest.mark.asyncio
@respx.mock
async def test_async_list_maps_thread_to_session_id(provider: AsyncAtomicMemoryProvider) -> None:
    route = respx.get("http://core.test/v1/memories/list").mock(
        return_value=httpx.Response(200, json={"memories": [], "count": 0}),
    )

    await provider.list(ListRequest(scope=Scope(user="u1", thread="thread-1"), limit=10))

    assert route.calls[0].request.url.params["session_id"] == "thread-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_health(provider: AsyncAtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )
    health = await provider.health()
    assert health.ok is True


@pytest.mark.asyncio
@respx.mock
async def test_async_package(provider: AsyncAtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [],
                "injection_text": "ctx\n",
                "estimated_context_tokens": 4,
                "budget_constrained": False,
            },
        )
    )
    pkg = await provider.package(PackageRequest(query="q", scope=Scope(user="u1")))
    assert pkg.text == "ctx\n"
    assert pkg.tokens == 4
    assert pkg.budget_constrained is False


@pytest.mark.asyncio
@respx.mock
async def test_async_package_maps_thread_to_session_id(provider: AsyncAtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={"memories": [], "injection_text": "", "estimated_context_tokens": 0, "budget_constrained": False},
        )
    )

    await provider.package(PackageRequest(query="q", scope=Scope(user="u1", thread="thread-1")))

    body = json.loads(route.calls[0].request.content)
    assert body["session_id"] == "thread-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_search_as_of_maps_thread_to_session_id(provider: AsyncAtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(200, json={"memories": []}),
    )

    await provider.search_as_of(
        SearchRequest(query="q", scope=Scope(user="u1", thread="thread-1")),
        datetime(2024, 6, 1, tzinfo=timezone.utc),
    )

    body = json.loads(route.calls[0].request.content)
    assert body["session_id"] == "thread-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_package_propagates_budget_constrained_true(
    provider: AsyncAtomicMemoryProvider,
) -> None:
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
    pkg = await provider.package(PackageRequest(query="q", scope=Scope(user="u1"), token_budget=5))
    assert pkg.budget_constrained is True


@pytest.mark.asyncio
@respx.mock
async def test_async_package_raises_when_budget_constrained_missing(
    provider: AsyncAtomicMemoryProvider,
) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={"memories": [], "injection_text": "", "estimated_context_tokens": 0},
        )
    )
    with pytest.raises(ValueError, match="budget_constrained"):
        await provider.package(PackageRequest(query="q", scope=Scope(user="u1")))


@pytest.mark.asyncio
@respx.mock
async def test_async_package_raises_when_budget_constrained_not_boolean(
    provider: AsyncAtomicMemoryProvider,
) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [],
                "injection_text": "",
                "estimated_context_tokens": 0,
                "budget_constrained": 1,
            },
        )
    )
    with pytest.raises(ValueError, match="budget_constrained"):
        await provider.package(PackageRequest(query="q", scope=Scope(user="u1")))


def test_async_capabilities_advertise_namespace() -> None:
    p = AsyncAtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    caps = p.capabilities()
    assert caps.custom_extensions is not None
    assert "atomicmemory.base" in caps.custom_extensions


@pytest.mark.asyncio
async def test_async_handle_categories_wired() -> None:
    p = AsyncAtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    await p.initialize()
    try:
        handle = p.get_extension("atomicmemory.base")
        assert isinstance(handle, AsyncAtomicMemoryHandle)
        assert handle.lifecycle is not None
        assert handle.audit is not None
        assert handle.lessons is not None
        assert handle.config is not None
        assert handle.agents is not None
    finally:
        await p.close()
