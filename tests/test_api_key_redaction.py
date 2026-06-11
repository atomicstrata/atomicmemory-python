"""Security tests: api_key must not appear in config repr/str.

Covers all three config models that carry credentials:
- EntitiesClientConfig
- StorageClientConfig
- AtomicMemoryClientConfig

Each model is tested for:
1. repr() and str() do NOT contain the raw secret.
2. The real Bearer token is sent in the Authorization header (proves
   .get_secret_value() is called at the header site, not the masked form).
"""

from __future__ import annotations

import httpx
import respx

from atomicmemory.client.atomic_memory_client import AtomicMemoryClientConfig
from atomicmemory.entities.client import EntitiesClient, EntitiesClientConfig
from atomicmemory.storage.client import StorageClient
from atomicmemory.storage.types import StorageClientConfig

_SECRET = "super-secret-api-key-12345"
_BASE_URL = "http://api.test"

# ---------------------------------------------------------------------------
# EntitiesClientConfig — repr redaction
# ---------------------------------------------------------------------------


def test_entities_config_repr_does_not_contain_secret() -> None:
    """repr() of EntitiesClientConfig must not expose the api_key."""
    config = EntitiesClientConfig(api_url=_BASE_URL, api_key=_SECRET)
    assert _SECRET not in repr(config)
    assert _SECRET not in str(config)


# ---------------------------------------------------------------------------
# StorageClientConfig — repr redaction
# ---------------------------------------------------------------------------


def test_storage_config_repr_does_not_contain_secret() -> None:
    """repr() of StorageClientConfig must not expose the api_key."""
    config = StorageClientConfig(api_url=_BASE_URL, api_key=_SECRET, user_id="u1")
    assert _SECRET not in repr(config)
    assert _SECRET not in str(config)


# ---------------------------------------------------------------------------
# AtomicMemoryClientConfig — repr redaction
# ---------------------------------------------------------------------------


def test_aggregator_config_repr_does_not_contain_secret() -> None:
    """repr() of AtomicMemoryClientConfig must not expose the api_key."""
    config = AtomicMemoryClientConfig(api_url=_BASE_URL, api_key=_SECRET, user_id="u1")
    assert _SECRET not in repr(config)
    assert _SECRET not in str(config)


# ---------------------------------------------------------------------------
# EntitiesClient — Bearer header uses actual key, not masked form
# ---------------------------------------------------------------------------


_PROFILE_WIRE: dict[str, object] = {
    "entity_type": "user",
    "entity_id": "alice",
    "profile": {"summary": "s", "preferences": [], "instructions": [], "open_commitments": []},
    "attributes": [],
    "memory_count": 0,
    "last_active": None,
    "updated_at": "2026-01-01T00:00:00Z",
}


@respx.mock
def test_entities_client_sends_real_bearer_token() -> None:
    """EntitiesClient sends the raw secret value in the Authorization header."""
    route = respx.get(f"{_BASE_URL}/v1/entities/user/alice/profile").mock(
        return_value=httpx.Response(200, json=_PROFILE_WIRE)
    )
    with EntitiesClient({"apiUrl": _BASE_URL, "apiKey": _SECRET}) as client:
        client.profile("alice")
    assert route.calls[0].request.headers["authorization"] == f"Bearer {_SECRET}"


@respx.mock
async def test_async_entities_client_sends_real_bearer_token() -> None:
    """AsyncEntitiesClient sends the raw secret value in the Authorization header."""
    from atomicmemory.entities.async_client import AsyncEntitiesClient

    route = respx.get(f"{_BASE_URL}/v1/entities/user/alice/profile").mock(
        return_value=httpx.Response(200, json=_PROFILE_WIRE)
    )
    async with AsyncEntitiesClient({"apiUrl": _BASE_URL, "apiKey": _SECRET}) as client:
        await client.profile("alice")
    assert route.calls[0].request.headers["authorization"] == f"Bearer {_SECRET}"


# ---------------------------------------------------------------------------
# StorageClient — Bearer header uses actual key, not masked form
# ---------------------------------------------------------------------------

_CAPABILITIES_WIRE: dict[str, object] = {
    "provider": "local_fs",
    "addressing": ["location"],
    "consistency": "immediate",
    "supportsDirectUpload": True,
    "supportsRangeRead": False,
    "supportsDelete": True,
    "supportsTombstone": False,
    "supportsBundles": False,
    "supportedBundleFormats": [],
    "supportsVerification": False,
    "supportsProviderProofs": False,
    "supportsReplication": False,
    "supportsRetrievalStatus": False,
    "supportsContentHash": False,
    "supportsContentAddressedUri": False,
    "deleteSemantics": ["delete"],
    "availabilityModel": "immediate",
}


@respx.mock
def test_storage_client_sends_real_bearer_token() -> None:
    """StorageClient sends the raw secret value in the Authorization header."""
    route = respx.get(f"{_BASE_URL}/v1/storage/capabilities").mock(
        return_value=httpx.Response(200, json=_CAPABILITIES_WIRE)
    )
    with StorageClient({"apiUrl": _BASE_URL, "apiKey": _SECRET, "userId": "u1"}) as client:
        client.capabilities()
    assert route.calls[0].request.headers["authorization"] == f"Bearer {_SECRET}"


@respx.mock
async def test_async_storage_client_sends_real_bearer_token() -> None:
    """AsyncStorageClient sends the raw secret value in the Authorization header."""
    from atomicmemory.storage.async_client import AsyncStorageClient

    route = respx.get(f"{_BASE_URL}/v1/storage/capabilities").mock(
        return_value=httpx.Response(200, json=_CAPABILITIES_WIRE)
    )
    async with AsyncStorageClient({"apiUrl": _BASE_URL, "apiKey": _SECRET, "userId": "u1"}) as client:
        await client.capabilities()
    assert route.calls[0].request.headers["authorization"] == f"Bearer {_SECRET}"
