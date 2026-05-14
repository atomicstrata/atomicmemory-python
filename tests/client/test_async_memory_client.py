"""Tests for AsyncMemoryClient — async mirror of the sync client tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from atomicmemory import (
    AsyncMemoryClient,
    AtomicMemoryError,
    ConfigError,
    NotInitializedError,
    Scope,
    SearchRequest,
    TextIngest,
    ValidationError,
)


@pytest.mark.asyncio
async def test_constructor_requires_provider_config() -> None:
    with pytest.raises(ConfigError):
        AsyncMemoryClient(providers={})


@pytest.mark.asyncio
async def test_calls_before_initialize_raise() -> None:
    client = AsyncMemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}})
    with pytest.raises(NotInitializedError):
        await client.search(SearchRequest(query="x", scope=Scope(user="u1")))


@pytest.mark.asyncio
@respx.mock
async def test_full_round_trip_via_default_provider() -> None:
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
    respx.post("http://core.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories": [{"id": "m-1", "content": "x", "ranking_score": 0.5, "created_at": "2024-01-01T00:00:00Z"}],
                "count": 1,
            },
        )
    )
    async with AsyncMemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        await client.initialize()
        ingest = await client.ingest(TextIngest(content="hi", scope=Scope(user="u1")))
        page = await client.search(SearchRequest(query="hi", scope=Scope(user="u1")))

    assert ingest.created == ["m-1"]
    assert page.results[0].memory.content == "x"


@pytest.mark.asyncio
async def test_dict_input_invalid_raises_sdk_validation_error() -> None:
    async with AsyncMemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        await client.initialize()
        with pytest.raises(ValidationError) as excinfo:
            await client.ingest({"mode": "bogus", "scope": {"user": "u1"}})
        assert isinstance(excinfo.value, AtomicMemoryError)


@pytest.mark.asyncio
@respx.mock
async def test_atomicmemory_handle_property_returns_async_handle() -> None:
    from atomicmemory.providers.atomicmemory.async_handle_impl import AsyncAtomicMemoryHandle

    async with AsyncMemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        await client.initialize()
        assert isinstance(client.atomicmemory, AsyncAtomicMemoryHandle)


@pytest.mark.asyncio
async def test_hindsight_provider_is_registered_async() -> None:
    async with AsyncMemoryClient(providers={"hindsight": {"api_url": "http://hindsight.test"}}) as client:
        await client.initialize()
        statuses = client.get_provider_status()

    assert statuses[0].name == "hindsight"
    assert statuses[0].initialized is True


@pytest.mark.asyncio
@respx.mock
async def test_dict_ingest_routes_through_to_provider() -> None:
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
    async with AsyncMemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        await client.initialize()
        result = await client.ingest({"mode": "text", "content": "hi", "scope": {"user": "u1"}})

    assert result.created == ["m-1"]
