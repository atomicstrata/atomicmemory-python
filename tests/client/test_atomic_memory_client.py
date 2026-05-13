"""Tests for the primary AtomicMemoryClient aggregator."""

from __future__ import annotations

import httpx
import pytest
import respx

from atomicmemory import AtomicMemoryClient, ConfigError
from tests.storage.test_storage_client import _capabilities


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
