"""Tests for sync HindsightProvider against a mocked Hindsight HTTP API."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.types import (
    ListRequest,
    MemoryRef,
    PackageRequest,
    Scope,
    SearchRequest,
    TextIngest,
    VerbatimIngest,
)
from atomicmemory.providers.hindsight.config import (
    HindsightOperationsHandle,
    HindsightProviderConfig,
    HindsightRetainHandle,
)
from atomicmemory.providers.hindsight.provider import HindsightProvider


@pytest.fixture
def provider() -> HindsightProvider:
    p = HindsightProvider(HindsightProviderConfig(api_url="http://hindsight.test"))
    p.initialize()
    yield p
    p.close()


@respx.mock
def test_ingest_returns_empty_created_and_posts_retain(provider: HindsightProvider) -> None:
    route = respx.post("http://hindsight.test/v1/default/banks/u1/memories").mock(
        return_value=httpx.Response(200, json={"success": True, "operation_id": "op-1"})
    )

    result = provider.ingest(TextIngest(content="hi", scope=Scope(user="u1", agent="sdk")))

    assert result.created == []
    body = json.loads(route.calls[0].request.content)
    assert body["items"][0]["tags"] == ["agent:sdk"]
    assert body["async"] is False


def test_ingest_verbatim_raises(provider: HindsightProvider) -> None:
    with pytest.raises(ProviderError, match="verbatim"):
        provider.ingest(VerbatimIngest(content="raw", scope=Scope(user="u1")))


@respx.mock
def test_search_truncates_limit_after_recall(provider: HindsightProvider) -> None:
    route = respx.post("http://hindsight.test/v1/default/banks/u1/memories/recall").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": "m-1", "text": "a", "created_at": "2024-01-01T00:00:00Z"},
                    {"id": "m-2", "text": "b", "created_at": "2024-01-02T00:00:00Z"},
                ]
            },
        )
    )

    page = provider.search(SearchRequest(query="q", scope=Scope(user="u1"), limit=1))

    body = json.loads(route.calls[0].request.content)
    assert body["max_tokens"] == 4096
    assert "limit" not in body
    assert [hit.memory.id for hit in page.results] == ["m-1"]


@respx.mock
def test_list_get_delete_routes(provider: HindsightProvider) -> None:
    respx.get("http://hindsight.test/v1/default/banks/u1/memories/list?limit=2&offset=0").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"id": "m-1", "text": "a", "date": "2024-01-01T00:00:00Z"},
                    {"id": "m-2", "text": "b", "date": "2024-01-02T00:00:00Z"},
                ],
                "total": 3,
            },
        )
    )
    respx.get("http://hindsight.test/v1/default/banks/u1/memories/m-1").mock(
        return_value=httpx.Response(200, json={"id": "m-1", "text": "a", "date": "2024-01-01T00:00:00Z"})
    )
    respx.delete("http://hindsight.test/v1/default/banks/u1/memories/missing").mock(return_value=httpx.Response(404))

    page = provider.list(ListRequest(scope=Scope(user="u1"), limit=2))
    found = provider.get(MemoryRef(id="m-1", scope=Scope(user="u1")))
    provider.delete(MemoryRef(id="missing", scope=Scope(user="u1")))

    assert page.cursor == "2"
    assert found is not None
    assert found.id == "m-1"


@respx.mock
def test_list_omits_cursor_when_total_is_exhausted(provider: HindsightProvider) -> None:
    respx.get("http://hindsight.test/v1/default/banks/u1/memories/list?limit=2&offset=0").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"id": "m-1", "text": "a", "date": "2024-01-01T00:00:00Z"},
                    {"id": "m-2", "text": "b", "date": "2024-01-02T00:00:00Z"},
                ],
                "total": 2,
            },
        )
    )

    page = provider.list(ListRequest(scope=Scope(user="u1"), limit=2))

    assert page.cursor is None


@respx.mock
def test_package_and_reflect_use_scope_tags(provider: HindsightProvider) -> None:
    package_route = respx.post("http://hindsight.test/v1/default/banks/u1/memories/recall").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": "m-1", "text": "a", "type": "world", "created_at": "2024-01-01T00:00:00Z"}]},
        )
    )
    reflect_route = respx.post("http://hindsight.test/v1/default/banks/u1/reflect").mock(
        return_value=httpx.Response(
            200, json={"text": "Alice validates AtomicMemory.", "based_on": {"memories": [{"id": "m-1"}]}}
        )
    )

    pkg = provider.package(PackageRequest(query="q", scope=Scope(user="u1", agent="sdk"), token_budget=128))
    insights = provider.reflect("q", Scope(user="u1", agent="sdk"))

    assert "Relevant memories:" in pkg.text
    assert pkg.tokens > 0
    assert json.loads(package_route.calls[0].request.content)["tags_match"] == "all_strict"
    assert json.loads(reflect_route.calls[0].request.content)["tags"] == ["agent:sdk"]
    assert insights[0].confidence == 0.0
    assert insights[0].supporting_memory_ids == ["m-1"]


@respx.mock
def test_package_uses_memory_label_when_hindsight_type_is_absent(provider: HindsightProvider) -> None:
    respx.post("http://hindsight.test/v1/default/banks/u1/memories/recall").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": "m-1", "text": "a", "created_at": "2024-01-01T00:00:00Z"}]},
        )
    )

    pkg = provider.package(PackageRequest(query="q", scope=Scope(user="u1")))

    assert pkg.text == "Relevant memories:\n- [memory] a"


@respx.mock
def test_health_maps_success_and_failure(provider: HindsightProvider) -> None:
    respx.get("http://hindsight.test/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy", "version": "0.6.1"})
    )
    assert provider.health().ok is True
    assert provider.health().version == "0.6.1"


@respx.mock
def test_custom_extensions_round_trip(provider: HindsightProvider) -> None:
    respx.post("http://hindsight.test/v1/default/banks/u1/memories").mock(
        return_value=httpx.Response(200, json={"success": True, "operation_id": "op-1"})
    )
    respx.get("http://hindsight.test/v1/default/banks/u1/operations/op-1").mock(
        return_value=httpx.Response(200, json={"operation_id": "op-1", "status": "processing"})
    )
    retain = provider.get_extension("hindsight.retain")
    operations = provider.get_extension("hindsight.operations")

    assert isinstance(retain, HindsightRetainHandle)
    assert isinstance(operations, HindsightOperationsHandle)
    retained = retain.retain(TextIngest(content="hi", scope=Scope(user="u1")))
    operation = operations.get(Scope(user="u1"), retained.operation_id or "")
    assert operation is not None
    assert operation.status == "processing"


@respx.mock
def test_retain_failure_has_context(provider: HindsightProvider) -> None:
    respx.post("http://hindsight.test/v1/default/banks/u1/memories").mock(
        return_value=httpx.Response(
            200, json={"success": False, "operation_id": "op-failed", "items_count": 2, "async": True}
        )
    )

    with pytest.raises(ProviderError, match="operation_id=op-failed, items_count=2, async=True"):
        provider.ingest(TextIngest(content="hi", scope=Scope(user="u1")))
