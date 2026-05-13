"""Tests for AtomicMemoryAgents category."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


@pytest.fixture
def provider() -> AtomicMemoryProvider:
    p = AtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    p.initialize()
    yield p
    p.close()


@respx.mock
def test_set_trust_includes_display_name(provider: AtomicMemoryProvider) -> None:
    route = respx.put("http://core.test/v1/agents/trust").mock(
        return_value=httpx.Response(200, json={"agent_id": "a1", "trust_level": 0.8})
    )
    result = provider._handle.agents.set_trust(  # type: ignore[union-attr]
        "u1", "a1", 0.8, display_name="Friendly Bot"
    )
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "user_id": "u1",
        "agent_id": "a1",
        "trust_level": 0.8,
        "display_name": "Friendly Bot",
    }
    assert result.trust_level == 0.8


@respx.mock
def test_get_trust_passes_query_params(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/agents/trust?user_id=u1&agent_id=a1").mock(
        return_value=httpx.Response(200, json={"agent_id": "a1", "trust_level": 0.5})
    )
    result = provider._handle.agents.get_trust("u1", "a1")  # type: ignore[union-attr]
    assert result.agent_id == "a1"


@respx.mock
def test_resolve_conflict_routes_by_conflict_id(provider: AtomicMemoryProvider) -> None:
    route = respx.put("http://core.test/v1/agents/conflicts/c-1/resolve").mock(
        return_value=httpx.Response(200, json={"id": "c-1", "status": "resolved_new"})
    )
    result = provider._handle.agents.resolve_conflict("c-1", "resolved_new")  # type: ignore[union-attr]
    assert result.status == "resolved_new"
    body = json.loads(route.calls[0].request.content)
    assert body == {"resolution": "resolved_new"}


@respx.mock
def test_auto_resolve_conflicts_returns_count(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/agents/conflicts/auto-resolve").mock(
        return_value=httpx.Response(200, json={"resolved": 7})
    )
    result = provider._handle.agents.auto_resolve_conflicts("u1")  # type: ignore[union-attr]
    assert result.resolved == 7
