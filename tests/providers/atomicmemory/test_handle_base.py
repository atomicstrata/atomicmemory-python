"""Tests for AtomicMemoryHandle base routes (ingest_full, search, expand, list, get, delete)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.core.errors import ValidationError
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.handle import (
    AtomicMemoryIngestInput,
    AtomicMemoryListOptions,
    AtomicMemorySearchRequest,
    UserScope,
    WorkspaceScope,
)
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


@pytest.fixture
def provider() -> AtomicMemoryProvider:
    p = AtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    p.initialize()
    yield p
    p.close()


def _ingest_response() -> dict[str, object]:
    return {
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
    }


@respx.mock
def test_ingest_full_workspace_includes_visibility(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/ingest").mock(
        return_value=httpx.Response(200, json=_ingest_response())
    )
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    handle.ingest_full(
        AtomicMemoryIngestInput(conversation="hi", source_site="chat", visibility="restricted"),
        WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1"),
    )

    body = json.loads(route.calls[0].request.content)
    assert body["workspace_id"] == "w1"
    assert body["agent_id"] == "a1"
    assert body["visibility"] == "restricted"


def test_ingest_user_scope_with_visibility_raises(provider: AtomicMemoryProvider) -> None:
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    with pytest.raises(ValidationError):
        handle.ingest_full(
            AtomicMemoryIngestInput(conversation="hi", source_site="chat", visibility="workspace"),
            UserScope(user_id="u1"),
        )


@respx.mock
def test_search_includes_agent_scope_in_body(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(200, json={"memories": [], "count": 0, "retrieval_mode": "flat"})
    )
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    handle.search(
        AtomicMemorySearchRequest(query="q"),
        WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", agent_scope="self"),
    )

    body = json.loads(route.calls[0].request.content)
    assert body["agent_scope"] == "self"


@respx.mock
def test_search_returns_namespace_typed_page(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "retrieval_mode": "flat",
                "memories": [
                    {
                        "id": "m-1",
                        "content": "x",
                        "created_at": "2024-01-01T00:00:00Z",
                        "ranking_score": 0.5,
                        "importance": 0.8,
                    }
                ],
                "injection_text": "x\n",
                "estimated_context_tokens": 5,
            },
        )
    )
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    page = handle.search(
        AtomicMemorySearchRequest(query="q"),
        UserScope(user_id="u1"),
    )

    assert page.count == 1
    assert page.results[0].importance == 0.8
    assert page.injection_text == "x\n"
    assert page.estimated_context_tokens == 5
    assert page.scope.kind == "user"


@respx.mock
def test_expand_strips_agent_scope_on_returned_memories(
    provider: AtomicMemoryProvider,
) -> None:
    respx.post("http://core.test/v1/memories/expand").mock(
        return_value=httpx.Response(
            200,
            json={"memories": [{"id": "m-1", "content": "a", "created_at": "2024-01-01T00:00:00Z"}]},
        )
    )
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    memories = handle.expand(
        ["m-1"],
        WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", agent_scope="self"),
    )

    assert len(memories) == 1
    assert isinstance(memories[0].scope, WorkspaceScope)
    assert memories[0].scope.agent_scope is None


def test_list_rejects_workspace_with_source_site(provider: AtomicMemoryProvider) -> None:
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    with pytest.raises(ValidationError):
        handle.list(
            WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1"),
            AtomicMemoryListOptions(source_site="chat"),
        )


@respx.mock
def test_get_returns_none_on_404_with_full_scope_echo(
    provider: AtomicMemoryProvider,
) -> None:
    respx.get(url__regex=r"http://core.test/v1/memories/m-x.*").mock(return_value=httpx.Response(404))
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    result = handle.get("m-x", UserScope(user_id="u1"))
    assert result is None


@respx.mock
def test_delete_swallows_404(provider: AtomicMemoryProvider) -> None:
    respx.delete(url__regex=r"http://core.test/v1/memories/m-x.*").mock(return_value=httpx.Response(404))
    handle = provider.get_extension("atomicmemory.base")
    assert handle is not None
    handle.delete("m-x", UserScope(user_id="u1"))
