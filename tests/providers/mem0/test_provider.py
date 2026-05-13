"""Tests for sync Mem0Provider end-to-end via respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.types import (
    ListRequest,
    MemoryRef,
    Scope,
    SearchRequest,
    TextIngest,
    VerbatimIngest,
)
from atomicmemory.providers.mem0.config import Mem0ProviderConfig
from atomicmemory.providers.mem0.provider import Mem0Provider


@pytest.fixture
def provider() -> Mem0Provider:
    p = Mem0Provider(Mem0ProviderConfig(api_url="http://mem0.test"))
    p.initialize()
    yield p
    p.close()


@respx.mock
def test_ingest_text_partitions_events(provider: Mem0Provider) -> None:
    route = respx.post("http://mem0.test/v1/memories/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "1", "memory": "hi", "event": "ADD"},
                {"id": "2", "memory": "hi again", "event": "UPDATE"},
            ],
        )
    )
    result = provider.ingest(TextIngest(content="hi", scope=Scope(user="u1")))
    assert result.created == ["1"]
    assert result.updated == ["2"]
    body = json.loads(route.calls[0].request.content)
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_ingest_verbatim_raises_unsupported(provider: Mem0Provider) -> None:
    with pytest.raises(ProviderError, match="verbatim"):
        provider.ingest(VerbatimIngest(content="hi", scope=Scope(user="u1")))


@respx.mock
def test_search_uses_v2_endpoint_for_hosted(provider: Mem0Provider) -> None:
    route = respx.post("http://mem0.test/v2/memories/search/").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": "m-1", "memory": "hit", "score": 0.7, "created_at": "2024-01-01T00:00:00Z"}]},
        )
    )
    page = provider.search(SearchRequest(query="q", scope=Scope(user="u1")))
    assert page.results[0].score == 0.7
    body = json.loads(route.calls[0].request.content)
    assert body["filters"] == {"user_id": "u1"}


@respx.mock
def test_search_uses_oss_endpoint_when_prefix_empty() -> None:
    p = Mem0Provider(Mem0ProviderConfig(api_url="http://mem0.test", path_prefix=""))
    p.initialize()
    try:
        respx.post("http://mem0.test/memories/search/").mock(
            return_value=httpx.Response(200, json=[]),
        )
        p.search(SearchRequest(query="q", scope=Scope(user="u1")))
    finally:
        p.close()


@respx.mock
def test_get_returns_none_on_404(provider: Mem0Provider) -> None:
    respx.get("http://mem0.test/v1/memories/m-x/").mock(return_value=httpx.Response(404))
    assert provider.get(MemoryRef(id="m-x", scope=Scope(user="u1"))) is None


@respx.mock
def test_delete_swallows_404(provider: Mem0Provider) -> None:
    respx.delete("http://mem0.test/v1/memories/m-x/").mock(return_value=httpx.Response(404))
    provider.delete(MemoryRef(id="m-x", scope=Scope(user="u1")))


@respx.mock
def test_list_paginates(provider: Mem0Provider) -> None:
    respx.get(url__regex=r"http://mem0.test/v1/memories/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": "1", "memory": "a", "created_at": "2024-01-01T00:00:00Z"},
                    {"id": "2", "memory": "b", "created_at": "2024-01-02T00:00:00Z"},
                ]
            },
        )
    )
    page = provider.list(ListRequest(scope=Scope(user="u1"), limit=2))
    assert page.cursor == "2"


def test_capabilities_excludes_verbatim_and_advertises_health(
    provider: Mem0Provider,
) -> None:
    caps = provider.capabilities()
    assert "verbatim" not in caps.ingest_modes
    assert caps.extensions.health is True
    assert caps.extensions.versioning is False


@respx.mock
def test_health_returns_true_on_success(provider: Mem0Provider) -> None:
    respx.get(url__regex=r"http://mem0.test/v1/memories/.*").mock(
        return_value=httpx.Response(200, json=[]),
    )
    assert provider.health().ok is True


@respx.mock
def test_health_returns_false_on_provider_error(provider: Mem0Provider) -> None:
    respx.get(url__regex=r"http://mem0.test/v1/memories/.*").mock(
        return_value=httpx.Response(500, json={"error": "down"}),
    )
    assert provider.health().ok is False
