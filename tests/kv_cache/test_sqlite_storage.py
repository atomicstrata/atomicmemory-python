"""Tests for SQLiteStorageAdapter — deterministic via injected clock."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from atomicmemory.core.errors import ConfigError
from atomicmemory.kv_cache import SQLiteStorageAdapter


@dataclass
class _MutableClock:
    now: float = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _store(clock: _MutableClock | None = None) -> SQLiteStorageAdapter:
    s = SQLiteStorageAdapter(clock=clock) if clock is not None else SQLiteStorageAdapter()
    s.initialize()
    return s


def test_set_get_round_trip_with_json() -> None:
    s = _store()
    s.set("k", {"nested": {"value": 1}})
    assert s.get("k") == {"nested": {"value": 1}}


def test_overwrite_existing_key() -> None:
    s = _store()
    s.set("k", 1)
    s.set("k", 2)
    assert s.get("k") == 2


def test_delete_returns_true_then_false() -> None:
    s = _store()
    s.set("k", 1)
    assert s.delete("k") is True
    assert s.delete("k") is False


def test_ttl_evicts_when_clock_advances() -> None:
    clock = _MutableClock()
    s = _store(clock)
    s.set("k", 1, ttl_seconds=10)
    assert s.get("k") == 1
    clock.advance(11)
    assert s.get("k") is None


def test_keys_sorted_and_size_consistent() -> None:
    s = _store()
    s.set("z", 1)
    s.set("a", 1)
    assert s.keys() == ["a", "z"]
    assert s.size() == 2


def test_vacuum_expired_returns_count() -> None:
    clock = _MutableClock()
    s = _store(clock)
    s.set("k", 1, ttl_seconds=1)
    clock.advance(2)
    assert s.vacuum_expired() == 1
    assert s.size() == 0


def test_close_releases_connection() -> None:
    s = _store()
    s.set("k", 1)
    s.close()


def test_set_with_encrypt_true_raises_config_error() -> None:
    s = _store()
    with pytest.raises(ConfigError, match="encryption"):
        s.set("k", "v", encrypt=True)


def test_persisted_expires_at_uses_wall_clock_epoch() -> None:
    """expires_at must be wall-clock so values survive a restart."""
    clock = _MutableClock(now=1_700_000_000.0)
    s = SQLiteStorageAdapter(db_path=":memory:", clock=clock)
    s.initialize()
    s.set("k", 1, ttl_seconds=60)
    row = s._require().execute("SELECT expires_at FROM atomicmemory_kv WHERE key = ?", ("k",)).fetchone()
    assert row[0] == 1_700_000_060.0
