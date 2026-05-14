"""Tests for AsyncHindsightProvider against a mocked Hindsight HTTP API."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from atomicmemory.memory.types import PackageRequest, Scope, SearchRequest, TextIngest
from atomicmemory.providers.hindsight.async_provider import AsyncHindsightProvider
from atomicmemory.providers.hindsight.config import (
    AsyncHindsightOperationsHandle,
    AsyncHindsightRetainHandle,
    HindsightProviderConfig,
)


@pytest_asyncio.fixture
async def provider() -> AsyncHindsightProvider:
    p = AsyncHindsightProvider(HindsightProviderConfig(api_url="http://hindsight.test"))
    await p.initialize()
    yield p
    await p.close()


@pytest.mark.asyncio
@respx.mock
async def test_async_search(provider: AsyncHindsightProvider) -> None:
    respx.post("http://hindsight.test/v1/default/banks/u1/memories/recall").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": "m-1", "text": "a", "created_at": "2024-01-01T00:00:00Z"}]},
        )
    )

    page = await provider.search(SearchRequest(query="q", scope=Scope(user="u1")))

    assert page.results[0].memory.id == "m-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_package_reflect_and_health(provider: AsyncHindsightProvider) -> None:
    respx.post("http://hindsight.test/v1/default/banks/u1/memories/recall").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": "m-1", "text": "a", "type": "world", "created_at": "2024-01-01T00:00:00Z"}]},
        )
    )
    respx.post("http://hindsight.test/v1/default/banks/u1/reflect").mock(
        return_value=httpx.Response(200, json={"text": "answer"})
    )
    respx.get("http://hindsight.test/health").mock(return_value=httpx.Response(200, json={"ok": True}))

    pkg = await provider.package(PackageRequest(query="q", scope=Scope(user="u1")))
    insight = (await provider.reflect("q", Scope(user="u1")))[0]
    health = await provider.health()

    assert pkg.text.startswith("Relevant memories:")
    assert insight.content == "answer"
    assert health.ok is True


@pytest.mark.asyncio
@respx.mock
async def test_async_custom_extensions(provider: AsyncHindsightProvider) -> None:
    respx.post("http://hindsight.test/v1/default/banks/u1/memories").mock(
        return_value=httpx.Response(200, json={"success": True, "operation_id": "op-1"})
    )
    respx.get("http://hindsight.test/v1/default/banks/u1/operations/op-1").mock(
        return_value=httpx.Response(200, json={"operation_id": "op-1", "status": "completed"})
    )
    retain = provider.get_extension("hindsight.retain")
    operations = provider.get_extension("hindsight.operations")

    assert isinstance(retain, AsyncHindsightRetainHandle)
    assert isinstance(operations, AsyncHindsightOperationsHandle)
    retained = await retain.retain(TextIngest(content="hi", scope=Scope(user="u1")))
    operation = await operations.get(Scope(user="u1"), retained.operation_id or "")
    assert operation is not None
    assert operation.status == "completed"
