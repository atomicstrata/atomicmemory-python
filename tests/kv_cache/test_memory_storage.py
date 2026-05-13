"""Tests for MemoryStorageAdapter — deterministic via injected clock."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from atomicmemory.core.errors import ConfigError
from atomicmemory.kv_cache import MemoryStorageAdapter


@dataclass
class _MutableClock:
    """Manually-advanceable clock for TTL tests."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_set_get_round_trip() -> None:
    store = MemoryStorageAdapter()
    store.initialize()
    store.set("k", {"value": 1})
    assert store.get("k") == {"value": 1}


def test_delete_returns_true_when_present() -> None:
    store = MemoryStorageAdapter()
    store.set("k", "v")
    assert store.delete("k") is True
    assert store.delete("k") is False


def test_ttl_expiry_evicts_when_clock_advances() -> None:
    clock = _MutableClock(now=1000.0)
    store = MemoryStorageAdapter(clock=clock)
    store.set("k", "v", ttl_seconds=10)
    assert store.has("k") is True
    clock.advance(15)
    assert store.has("k") is False


def test_keys_returns_only_live_entries() -> None:
    clock = _MutableClock(now=0.0)
    store = MemoryStorageAdapter(clock=clock)
    store.set("a", 1)
    store.set("b", 2, ttl_seconds=5)
    clock.advance(10)
    assert store.keys() == ["a"]


def test_size_excludes_expired() -> None:
    clock = _MutableClock(now=0.0)
    store = MemoryStorageAdapter(clock=clock)
    store.set("a", 1)
    store.set("b", 2, ttl_seconds=5)
    clock.advance(10)
    assert store.size() == 1


def test_clear_removes_everything() -> None:
    store = MemoryStorageAdapter()
    store.set("a", 1)
    store.set("b", 2)
    store.clear()
    assert store.size() == 0


def test_set_with_encrypt_true_raises_config_error() -> None:
    """Encryption is not implemented — fail closed instead of silently storing plaintext."""
    store = MemoryStorageAdapter()
    with pytest.raises(ConfigError, match="encryption"):
        store.set("k", "v", encrypt=True)
