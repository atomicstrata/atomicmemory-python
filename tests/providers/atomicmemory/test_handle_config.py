"""Tests for AtomicMemoryConfig category."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.handle import ConfigUpdates
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


@pytest.fixture
def provider() -> AtomicMemoryProvider:
    p = AtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    p.initialize()
    yield p
    p.close()


_HEALTH_CONFIG = {
    "retrieval_profile": "default",
    "embedding_provider": "openai",
    "embedding_model": "text-embedding-3-small",
    "llm_provider": "openai",
    "llm_model": "gpt-4o",
    "clarification_conflict_threshold": 0.7,
    "max_search_results": 20,
    "hybrid_search_enabled": True,
    "iterative_retrieval_enabled": False,
    "entity_graph_enabled": True,
    "cross_encoder_enabled": False,
    "agentic_retrieval_enabled": False,
    "repair_loop_enabled": True,
}


@respx.mock
def test_health_decodes_typed_status(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "config": _HEALTH_CONFIG})
    )
    health = provider._handle.config.health()  # type: ignore[union-attr]
    assert health.config.embedding_provider == "openai"
    assert health.config.max_search_results == 20


@respx.mock
def test_update_config_camelizes_applied_field_names(
    provider: AtomicMemoryProvider,
) -> None:
    route = respx.put("http://core.test/v1/memories/config").mock(
        return_value=httpx.Response(
            200,
            json={
                "applied": ["max_search_results", "audn_candidate_threshold"],
                "config": _HEALTH_CONFIG,
                "note": "ok",
            },
        )
    )
    result = provider._handle.config.update_config(  # type: ignore[union-attr]
        ConfigUpdates(max_search_results=25, audn_candidate_threshold=0.4)
    )
    assert result.applied == ["maxSearchResults", "audnCandidateThreshold"]
    body = json.loads(route.calls[0].request.content)
    assert body == {"max_search_results": 25, "audn_candidate_threshold": 0.4}


@respx.mock
def test_update_config_accepts_dict_input(provider: AtomicMemoryProvider) -> None:
    respx.put("http://core.test/v1/memories/config").mock(
        return_value=httpx.Response(
            200,
            json={"applied": [], "config": _HEALTH_CONFIG, "note": ""},
        )
    )
    result = provider._handle.config.update_config(  # type: ignore[union-attr]
        {"similarityThreshold": 0.55}
    )
    assert result.config.embedding_model == "text-embedding-3-small"
