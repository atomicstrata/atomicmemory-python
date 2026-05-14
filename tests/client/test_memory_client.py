"""End-to-end tests for the sync MemoryClient via the AtomicMemory provider."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import ValidationError as PydanticValidationError

from atomicmemory import (
    AtomicMemoryError,
    ConfigError,
    MemoryClient,
    MemoryRef,
    NotInitializedError,
    Scope,
    SearchRequest,
    TextIngest,
    ValidationError,
)


def test_constructor_requires_provider_config() -> None:
    with pytest.raises(ConfigError, match="at least one provider"):
        MemoryClient(providers={})


def test_calls_before_initialize_raise() -> None:
    client = MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}})
    with pytest.raises(NotInitializedError):
        client.search(SearchRequest(query="x", scope=Scope(user="u1")))


@respx.mock
def test_full_round_trip_via_default_provider() -> None:
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
                "memories": [
                    {
                        "id": "m-1",
                        "content": "aisles",
                        "ranking_score": 0.5,
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "count": 1,
            },
        )
    )
    respx.delete("http://core.test/v1/memories/m-1").mock(return_value=httpx.Response(204))

    with MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        client.initialize()
        ingest_result = client.ingest(TextIngest(content="I prefer aisles", scope=Scope(user="u1")))
        page = client.search(SearchRequest(query="aisles", scope=Scope(user="u1")))
        client.delete(MemoryRef(id="m-1", scope=Scope(user="u1")))

    assert ingest_result.created == ["m-1"]
    assert page.results[0].memory.content == "aisles"


def test_provider_status_reports_uninitialized() -> None:
    client = MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}})
    statuses = client.get_provider_status()
    assert len(statuses) == 1
    assert statuses[0].name == "atomicmemory"
    assert statuses[0].initialized is False


@respx.mock
def test_provider_status_after_initialize_reports_capabilities() -> None:
    with MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        client.initialize()
        statuses = client.get_provider_status()

    assert statuses[0].initialized is True
    assert statuses[0].capabilities is not None
    assert "verbatim" in statuses[0].capabilities.ingest_modes


def test_hindsight_provider_is_registered() -> None:
    with MemoryClient(providers={"hindsight": {"api_url": "http://hindsight.test"}}) as client:
        client.initialize()
        statuses = client.get_provider_status()

    assert statuses[0].name == "hindsight"
    assert statuses[0].initialized is True


@respx.mock
def test_atomicmemory_property_returns_handle_when_provider_configured() -> None:
    from atomicmemory.providers.atomicmemory.handle_impl import AtomicMemoryHandle

    with MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        client.initialize()
        handle = client.atomicmemory
        assert isinstance(handle, AtomicMemoryHandle)
        assert handle.lifecycle is not None
        assert handle.audit is not None
        assert handle.lessons is not None
        assert handle.config is not None
        assert handle.agents is not None


@respx.mock
def test_ingest_accepts_plain_dict() -> None:
    """README and docstring promise dict input; client must coerce."""
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
    with MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        client.initialize()
        result = client.ingest({"mode": "text", "content": "hi", "scope": {"user": "u1"}})

    assert result.created == ["m-1"]


@respx.mock
def test_search_accepts_plain_dict() -> None:
    respx.post("http://core.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(200, json={"memories": [], "count": 0}),
    )
    with MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        client.initialize()
        page = client.search({"query": "x", "scope": {"user": "u1"}})

    assert page.results == []


@respx.mock
def test_get_and_delete_accept_plain_dict() -> None:
    respx.get("http://core.test/v1/memories/m-1").mock(return_value=httpx.Response(404))
    respx.delete("http://core.test/v1/memories/m-1").mock(return_value=httpx.Response(204))
    with MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}}) as client:
        client.initialize()
        assert client.get({"id": "m-1", "scope": {"user": "u1"}}) is None
        client.delete({"id": "m-1", "scope": {"user": "u1"}})


def _initialized_client() -> MemoryClient:
    """Build a client and initialize it without making any HTTP calls."""
    client = MemoryClient(providers={"atomicmemory": {"api_url": "http://core.test"}})
    client.initialize()
    return client


def test_ingest_invalid_mode_raises_sdk_validation_error() -> None:
    client = _initialized_client()
    try:
        with pytest.raises(ValidationError) as excinfo:
            client.ingest({"mode": "bogus", "content": "x", "scope": {"user": "u1"}})
        assert isinstance(excinfo.value, AtomicMemoryError)
        assert not isinstance(excinfo.value, PydanticValidationError)
        assert excinfo.value.context["type"] == "IngestInput"
        assert excinfo.value.context["errors"]
    finally:
        client.close()


def test_ingest_unknown_top_level_field_raises_sdk_validation_error() -> None:
    client = _initialized_client()
    try:
        with pytest.raises(ValidationError) as excinfo:
            client.ingest(
                {"mode": "text", "content": "hi", "scope": {"user": "u1"}, "junk": True},
            )
        assert excinfo.value.context["type"] == "IngestInput"
    finally:
        client.close()


def test_search_invalid_dict_raises_sdk_validation_error() -> None:
    client = _initialized_client()
    try:
        with pytest.raises(ValidationError) as excinfo:
            client.search({"scope": {"user": "u1"}})  # missing required `query`
        assert excinfo.value.context["type"] == "SearchRequest"
    finally:
        client.close()


def test_get_invalid_dict_raises_sdk_validation_error() -> None:
    client = _initialized_client()
    try:
        with pytest.raises(ValidationError) as excinfo:
            client.get({"id": "m-1"})  # missing required `scope`
        assert excinfo.value.context["type"] == "MemoryRef"
    finally:
        client.close()


def test_list_invalid_dict_raises_sdk_validation_error() -> None:
    client = _initialized_client()
    try:
        with pytest.raises(ValidationError) as excinfo:
            client.list({"scope": {"user": "u1"}, "junk": True})
        assert excinfo.value.context["type"] == "ListRequest"
    finally:
        client.close()


def test_package_invalid_dict_raises_sdk_validation_error() -> None:
    client = _initialized_client()
    try:
        with pytest.raises(ValidationError) as excinfo:
            client.package({"scope": {"user": "u1"}})  # missing `query`
        assert excinfo.value.context["type"] == "PackageRequest"
    finally:
        client.close()
