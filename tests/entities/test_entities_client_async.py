"""Tests for the async EntitiesClient over /v1/entities.

Mirrors every behaviour test in ``tests/entities/test_entities_client.py``,
but uses ``AsyncEntitiesClient`` and the respx async idiom from
``tests/storage/test_async_storage_client.py``.

asyncio_mode = "auto" (set globally in pyproject.toml) means no explicit
``@pytest.mark.asyncio`` decorators are needed.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.entities import (
    DeleteEntityResult,
    EntityDetail,
    EntityListResult,
    EntityProfile,
    EntitySettings,
    MemoryHistory,
    MergeEntitiesResult,
)
from atomicmemory.entities.async_client import AsyncEntitiesClient
from atomicmemory.entities.errors import EntitiesClientError

# ---------------------------------------------------------------------------
# Fixtures / shared wire payloads (mirrored from sync tests)
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.test"
_API_KEY = "test-key"


def _make_client(api_url: str = _BASE_URL) -> AsyncEntitiesClient:
    return AsyncEntitiesClient({"apiUrl": api_url, "apiKey": _API_KEY})


_PROFILE_WIRE: dict[str, object] = {
    "entity_type": "user",
    "entity_id": "alice",
    "profile": {
        "summary": "s",
        "preferences": ["p1"],
        "instructions": [],
        "open_commitments": [],
    },
    "attributes": [],
    "memory_count": 1,
    "last_active": None,
    "updated_at": "2026-06-01T00:00:00Z",
}

_LIST_WIRE: dict[str, object] = {
    "entities": [{"entity_type": "user", "entity_id": "alice", "memory_count": 1, "last_active": None}],
    "total": 1,
    "page": 1,
    "page_size": 20,
}

_DETAIL_WIRE: dict[str, object] = {
    "entity_type": "user",
    "entity_id": "alice",
    "memory_count": 2,
    "attributes": [],
    "relations": [],
    "recent_cards": [],
    "updated_at": None,
}

_DELETE_WIRE: dict[str, object] = {
    "deleted": {
        "memories": 3,
        "entity_attributes": 5,
        "profile": 1,
        "entities": 1,
        "entity_edges": 2,
        "entity_cards": 4,
    }
}

_ATTRS_WIRE: dict[str, object] = {
    "attributes": [
        {
            "entity": "alice",
            "attribute": "role",
            "value": "admin",
            "type": "string",
            "source_memory_id": None,
            "observed_at": "2026-06-01T00:00:00Z",
        }
    ]
}

_HISTORY_WIRE: dict[str, object] = {
    "memory_id": "m1",
    "history": [
        {
            "version_id": "v1",
            "event": "created",
            "content": "text",
            "timestamp": "2026-06-01T00:00:00Z",
            "superseded_by": None,
        }
    ],
}

_SETTINGS_WIRE: dict[str, object] = {
    "entity_id": "alice",
    "extraction_prompt": None,
    "memory_kinds": None,
    "decay_enabled": False,
    "updated_at": "2026-06-01T00:00:00Z",
}

_MERGE_WIRE: dict[str, object] = {
    "merged": {"memories_moved": 3, "attributes_moved": 2, "cards_moved": 1},
    "target_entity_id": "bob",
}

# ---------------------------------------------------------------------------
# Auth + path tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_async_profile_requests_correct_path_with_bearer_auth() -> None:
    """profile() hits the right URL and sends Bearer token."""
    route = respx.get(f"{_BASE_URL}/v1/entities/user/alice/profile").mock(
        return_value=httpx.Response(200, json=_PROFILE_WIRE)
    )
    async with _make_client() as client:
        profile = await client.profile("alice")
    request = route.calls[0].request
    assert request.headers["authorization"] == f"Bearer {_API_KEY}"
    assert isinstance(profile, EntityProfile)
    assert profile.entity_id == "alice"


@respx.mock
async def test_async_entity_id_is_url_encoded_in_paths() -> None:
    """Special characters in entity_id are percent-encoded in the path."""
    route = respx.get(f"{_BASE_URL}/v1/entities/user/a%2Fb%20c/profile").mock(
        return_value=httpx.Response(200, json=_PROFILE_WIRE)
    )
    async with _make_client() as client:
        await client.profile("a/b c")
    assert route.called


@respx.mock
async def test_async_list_with_no_options_sends_no_query_params() -> None:
    """list() with no opts sends no query string."""
    route = respx.get(f"{_BASE_URL}/v1/entities").mock(return_value=httpx.Response(200, json=_LIST_WIRE))
    async with _make_client() as client:
        result = await client.list()
    assert isinstance(result, EntityListResult)
    assert "entity_type" not in str(route.calls[0].request.url)
    assert "page" not in str(route.calls[0].request.url)


@respx.mock
async def test_async_list_with_options_sends_query_params() -> None:
    """list() with opts serialises only the provided params."""
    route = respx.get(f"{_BASE_URL}/v1/entities").mock(return_value=httpx.Response(200, json=_LIST_WIRE))
    async with _make_client() as client:
        await client.list(entity_type="agent", page=2, page_size=10)
    url_str = str(route.calls[0].request.url)
    assert "entity_type=agent" in url_str
    assert "page=2" in url_str
    assert "page_size=10" in url_str


@respx.mock
async def test_async_get_entity_detail() -> None:
    """get() hits GET /v1/entities/{type}/{id}."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice").mock(return_value=httpx.Response(200, json=_DETAIL_WIRE))
    async with _make_client() as client:
        result = await client.get("alice")
    assert isinstance(result, EntityDetail)
    assert result.entity_id == "alice"


@respx.mock
async def test_async_delete_returns_six_counts() -> None:
    """delete() hits DELETE and returns DeleteEntityResult with six counts."""
    respx.delete(f"{_BASE_URL}/v1/entities/user/alice").mock(return_value=httpx.Response(200, json=_DELETE_WIRE))
    async with _make_client() as client:
        result = await client.delete("alice")
    assert isinstance(result, DeleteEntityResult)
    assert result.deleted.memories == 3
    assert result.deleted.entity_attributes == 5
    assert result.deleted.profile == 1
    assert result.deleted.entities == 1
    assert result.deleted.entity_edges == 2
    assert result.deleted.entity_cards == 4


@respx.mock
async def test_async_attributes_unwraps_envelope() -> None:
    """attributes() unwraps the {'attributes': [...]} envelope."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice/attributes").mock(return_value=httpx.Response(200, json=_ATTRS_WIRE))
    async with _make_client() as client:
        attrs = await client.attributes("alice")
    assert len(attrs) == 1
    assert attrs[0].attribute == "role"


@respx.mock
async def test_async_attributes_absent_key_returns_empty_list() -> None:
    """attributes() returns [] when the response has no 'attributes' key."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice/attributes").mock(return_value=httpx.Response(200, json={}))
    async with _make_client() as client:
        result = await client.attributes("alice")
    assert result == []


@respx.mock
async def test_async_attributes_query_params_only_when_provided() -> None:
    """attributes() omits params not passed by the caller."""
    route = respx.get(f"{_BASE_URL}/v1/entities/user/alice/attributes").mock(
        return_value=httpx.Response(200, json=_ATTRS_WIRE)
    )
    async with _make_client() as client:
        await client.attributes("alice", attribute="role", limit=5)
    url_str = str(route.calls[0].request.url)
    assert "attribute=role" in url_str
    assert "limit=5" in url_str
    assert "entity=" not in url_str


@respx.mock
async def test_async_memory_history_path_includes_encoded_memory_id() -> None:
    """memory_history() encodes both entity_id and memory_id in the path."""
    route = respx.get(f"{_BASE_URL}/v1/entities/user/alice/memories/m%2F1/history").mock(
        return_value=httpx.Response(200, json=_HISTORY_WIRE)
    )
    async with _make_client() as client:
        result = await client.memory_history("alice", "m/1")
    assert isinstance(result, MemoryHistory)
    assert route.called


@respx.mock
async def test_async_patch_settings_sends_only_provided_fields() -> None:
    """patch_settings() body includes ONLY the kwargs supplied."""
    route = respx.patch(f"{_BASE_URL}/v1/entities/user/alice/settings").mock(
        return_value=httpx.Response(200, json=_SETTINGS_WIRE)
    )
    async with _make_client() as client:
        result = await client.patch_settings("alice", extraction_prompt="focus on prefs")
    sent = json.loads(route.calls[0].request.content)
    assert sent == {"extraction_prompt": "focus on prefs"}
    assert isinstance(result, EntitySettings)


@respx.mock
async def test_async_patch_settings_with_all_fields() -> None:
    """patch_settings() with all three fields sends all three snake-case keys."""
    route = respx.patch(f"{_BASE_URL}/v1/entities/user/alice/settings").mock(
        return_value=httpx.Response(200, json=_SETTINGS_WIRE)
    )
    async with _make_client() as client:
        await client.patch_settings(
            "alice",
            extraction_prompt="ep",
            memory_kinds=["episodic"],
            decay_enabled=True,
        )
    sent = json.loads(route.calls[0].request.content)
    assert sent == {
        "extraction_prompt": "ep",
        "memory_kinds": ["episodic"],
        "decay_enabled": True,
    }


@respx.mock
async def test_async_patch_settings_decay_enabled_false_is_sent() -> None:
    """patch_settings(decay_enabled=False) must send the falsy value, not drop it."""
    route = respx.patch(f"{_BASE_URL}/v1/entities/user/alice/settings").mock(
        return_value=httpx.Response(200, json=_SETTINGS_WIRE)
    )
    async with _make_client() as client:
        await client.patch_settings("alice", decay_enabled=False)
    sent = json.loads(route.calls[0].request.content)
    assert sent == {"decay_enabled": False}


@respx.mock
async def test_async_list_page_zero_is_sent() -> None:
    """list(page=0) must serialise the falsy page value into the query string."""
    route = respx.get(f"{_BASE_URL}/v1/entities").mock(return_value=httpx.Response(200, json=_LIST_WIRE))
    async with _make_client() as client:
        await client.list(page=0)
    assert "page=0" in str(route.calls[0].request.url)


@respx.mock
async def test_async_merge_body_shape_with_defaults() -> None:
    """merge() builds the correct body and entity_type defaults to 'user'."""
    route = respx.post(f"{_BASE_URL}/v1/entities/merge").mock(return_value=httpx.Response(200, json=_MERGE_WIRE))
    async with _make_client() as client:
        result = await client.merge("alice", "bob")
    sent = json.loads(route.calls[0].request.content)
    assert sent == {
        "source": {"entity_type": "user", "entity_id": "alice"},
        "target": {"entity_type": "user", "entity_id": "bob"},
    }
    assert isinstance(result, MergeEntitiesResult)
    assert result.target_entity_id == "bob"


@respx.mock
async def test_async_merge_with_explicit_entity_types() -> None:
    """merge() passes through explicit entity_type values."""
    route = respx.post(f"{_BASE_URL}/v1/entities/merge").mock(return_value=httpx.Response(200, json=_MERGE_WIRE))
    async with _make_client() as client:
        await client.merge("alice", "bob", source_entity_type="agent", target_entity_type="session")
    sent = json.loads(route.calls[0].request.content)
    assert sent["source"]["entity_type"] == "agent"
    assert sent["target"]["entity_type"] == "session"


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_async_non_2xx_raises_entities_error_with_method_path_status_body() -> None:
    """Non-2xx response raises EntitiesClientError with method+path+status+body."""
    respx.get(f"{_BASE_URL}/v1/entities/user/missing/profile").mock(return_value=httpx.Response(404, text="not found"))
    with pytest.raises(EntitiesClientError) as exc_info:
        async with _make_client() as client:
            await client.profile("missing")
    msg = str(exc_info.value)
    assert "GET" in msg
    assert "/v1/entities/user/missing/profile" in msg
    assert "404" in msg
    assert "not found" in msg


@respx.mock
async def test_async_network_failure_raises_entities_error_with_cause() -> None:
    """Network failure (ConnectError) is wrapped in EntitiesClientError."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice/profile").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(EntitiesClientError) as exc_info:
        async with _make_client() as client:
            await client.profile("alice")
    assert exc_info.value.error_code == "network_error"


async def test_async_trailing_slash_api_url_is_normalized() -> None:
    """Trailing slashes in api_url are stripped."""
    client = AsyncEntitiesClient({"apiUrl": "https://api.test///", "apiKey": "k"})
    assert not client._api_url.endswith("/")  # type: ignore[attr-defined]


@respx.mock
async def test_async_no_extra_user_id_header_sent() -> None:
    """AsyncEntitiesClient must NOT send X-AtomicMemory-User-Id."""
    route = respx.get(f"{_BASE_URL}/v1/entities/user/alice/profile").mock(
        return_value=httpx.Response(200, json=_PROFILE_WIRE)
    )
    async with _make_client() as client:
        await client.profile("alice")
    assert "x-atomicmemory-user-id" not in {k.lower() for k in route.calls[0].request.headers}
