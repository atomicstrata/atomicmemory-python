"""Tests for the primary AtomicMemoryClient aggregator."""

from __future__ import annotations

import httpx
import pytest
import respx

from atomicmemory import AsyncAtomicMemoryClient, AtomicMemoryClient, ConfigError
from atomicmemory.entities import AsyncEntitiesClient, EntitiesClient
from tests.storage.test_storage_client import _capabilities

_BASE_CONFIG = {"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}


def test_atomic_memory_client_requires_transport_fields() -> None:
    with pytest.raises(ConfigError):
        AtomicMemoryClient({"apiUrl": "http://core.test", "apiKey": "", "userId": "u1"})


def test_atomic_memory_client_validation_does_not_leak_secret_inputs() -> None:
    with pytest.raises(ConfigError) as excinfo:
        AtomicMemoryClient({"apiUrl": "not-a-url", "apiKey": "secret-key", "userId": "u1"})

    assert "secret-key" not in str(excinfo.value.context)


@respx.mock
def test_atomic_memory_client_exposes_memory_and_storage_namespaces() -> None:
    route = respx.get("http://core.test/v1/storage/capabilities").mock(
        return_value=httpx.Response(200, json=_capabilities()),
    )
    with AtomicMemoryClient({"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}) as client:
        client.memory.initialize()
        caps = client.storage.capabilities()

    assert caps.provider == "local_fs"
    assert route.calls[0].request.headers["Authorization"] == "Bearer secret"


@respx.mock
def test_atomic_memory_client_accepts_typescript_memory_config_shape() -> None:
    search_route = respx.post("http://memory.test/v1/memories/search/fast").mock(
        return_value=httpx.Response(200, json={"memories": [], "count": 0}),
    )
    config = {
        "apiUrl": "http://core.test",
        "apiKey": "storage-secret",
        "userId": "u1",
        "memory": {"providers": {"atomicmemory": {"apiUrl": "http://memory.test", "apiKey": "memory-secret"}}},
    }
    with AtomicMemoryClient(config) as client:
        client.memory.initialize()
        page = client.memory.search({"query": "x", "scope": {"user": "u1"}})

    assert page.results == []
    assert search_route.calls[0].request.headers["Authorization"] == "Bearer memory-secret"


def test_atomic_memory_client_rejects_legacy_flat_memory_config_shape() -> None:
    with pytest.raises(ConfigError) as excinfo:
        AtomicMemoryClient(
            {
                "apiUrl": "http://core.test",
                "apiKey": "secret",
                "userId": "u1",
                "memory": {"atomicmemory": {"apiUrl": "http://memory.test"}},
            }
        )

    assert excinfo.value.context["errors"]


def test_atomic_memory_client_close_attempts_both_namespaces(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AtomicMemoryClient({"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"})
    storage_closed = False

    def close_memory() -> None:
        raise RuntimeError("memory close failed")

    def close_storage() -> None:
        nonlocal storage_closed
        storage_closed = True

    monkeypatch.setattr(client.memory, "close", close_memory)
    monkeypatch.setattr(client.storage, "close", close_storage)
    with pytest.raises(RuntimeError, match="memory close failed"):
        client.close()

    assert storage_closed is True


# ---------------------------------------------------------------------------
# Entities namespace — sync aggregator
# ---------------------------------------------------------------------------


def test_atomic_memory_client_exposes_entities_namespace() -> None:
    client = AtomicMemoryClient(_BASE_CONFIG)
    assert isinstance(client.entities, EntitiesClient)


def test_atomic_memory_client_entities_uses_same_transport_config() -> None:
    client = AtomicMemoryClient(_BASE_CONFIG)
    assert client.entities._config.api_url == "http://core.test"
    assert client.entities._config.api_key.get_secret_value() == "secret"
    assert client.entities._config.timeout_seconds == 30.0


def test_atomic_memory_client_close_also_closes_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AtomicMemoryClient(_BASE_CONFIG)
    entities_closed = False

    def close_memory() -> None:
        raise RuntimeError("memory close failed")

    def close_entities() -> None:
        nonlocal entities_closed
        entities_closed = True

    monkeypatch.setattr(client.memory, "close", close_memory)
    monkeypatch.setattr(client.entities, "close", close_entities)
    with pytest.raises(RuntimeError, match="memory close failed"):
        client.close()

    assert entities_closed is True


# ---------------------------------------------------------------------------
# Entities namespace — async aggregator
# ---------------------------------------------------------------------------


def test_async_atomic_memory_client_exposes_entities_namespace() -> None:
    client = AsyncAtomicMemoryClient(_BASE_CONFIG)
    assert isinstance(client.entities, AsyncEntitiesClient)


def test_async_atomic_memory_client_entities_uses_same_transport_config() -> None:
    client = AsyncAtomicMemoryClient(_BASE_CONFIG)
    assert client.entities._config.api_url == "http://core.test"
    assert client.entities._config.api_key.get_secret_value() == "secret"
    assert client.entities._config.timeout_seconds == 30.0


async def test_async_atomic_memory_client_close_also_closes_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncAtomicMemoryClient(_BASE_CONFIG)
    entities_closed = False

    async def async_close_memory() -> None:
        raise RuntimeError("memory close failed")

    async def async_close_entities() -> None:
        nonlocal entities_closed
        entities_closed = True

    monkeypatch.setattr(client.memory, "close", async_close_memory)
    monkeypatch.setattr(client.entities, "close", async_close_entities)
    with pytest.raises(RuntimeError, match="memory close failed"):
        await client.close()

    assert entities_closed is True


async def test_async_close_reaches_entities_when_memory_and_storage_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncAtomicMemoryClient(_BASE_CONFIG)
    entities_closed = False

    async def async_close_memory() -> None:
        raise RuntimeError("memory close failed")

    async def async_close_storage() -> None:
        raise RuntimeError("storage close failed")

    async def async_close_entities() -> None:
        nonlocal entities_closed
        entities_closed = True

    monkeypatch.setattr(client.memory, "close", async_close_memory)
    monkeypatch.setattr(client.storage, "close", async_close_storage)
    monkeypatch.setattr(client.entities, "close", async_close_entities)
    with pytest.raises(RuntimeError, match="memory close failed"):  # first error wins
        await client.close()

    assert entities_closed is True


def test_sync_close_first_error_wins_and_reaches_entities() -> None:
    # Twin of the async both-fail test: memory's error must surface (not be
    # replaced by storage's) and entities must still close.
    client = AtomicMemoryClient(_BASE_CONFIG)
    entities_closed = []

    def fail_memory() -> None:
        raise RuntimeError("memory close failed")

    def fail_storage() -> None:
        raise RuntimeError("storage close failed")

    client.memory.close = fail_memory  # type: ignore[method-assign]
    client.storage.close = fail_storage  # type: ignore[method-assign]
    client.entities.close = lambda: entities_closed.append(True)  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="memory close failed"):
        client.close()
    assert entities_closed == [True]
