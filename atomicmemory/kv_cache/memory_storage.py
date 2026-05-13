"""In-memory key/value cache adapter.

Port of `atomicmemory-sdk/src/kv-cache/memory-storage.ts`. Threaded
access is **not** safe; if you need concurrent writers, wrap your own
lock or use the SQLite adapter.

The TTL clock is injectable: pass ``clock=`` to use a deterministic
callable in tests. Defaults to :func:`time.monotonic` so wall-clock
changes don't affect in-memory expiry.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from atomicmemory.core.errors import ConfigError


@dataclass
class _MemoryItem:
    value: Any
    created_at: float
    expires_at: float | None


class MemoryStorageAdapter:
    """Pure-Python in-memory store with TTL support."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._data: dict[str, _MemoryItem] = {}
        self._clock: Callable[[], float] = clock or time.monotonic

    def initialize(self) -> None:
        """No-op; the dict is ready to use as soon as the adapter is constructed."""

    def close(self) -> None:
        self._data.clear()

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item.expires_at is not None and self._clock() >= item.expires_at:
            del self._data[key]
            return None
        return item.value

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: float | None = None,
        encrypt: bool = False,
    ) -> None:
        if encrypt:
            raise ConfigError(
                "MemoryStorageAdapter does not implement encryption; "
                "passing encrypt=True would silently store plaintext. "
                "Omit the flag or use a backend that implements ciphered storage.",
                context={"adapter": "MemoryStorageAdapter"},
            )
        now = self._clock()
        self._data[key] = _MemoryItem(
            value=value,
            created_at=now,
            expires_at=now + ttl_seconds if ttl_seconds is not None else None,
        )

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self) -> list[str]:
        # Materialize the list and drop expired entries on the way through
        # so callers don't see stale ids.
        live: list[str] = []
        now = self._clock()
        expired: list[str] = []
        for key, item in self._data.items():
            if item.expires_at is not None and now >= item.expires_at:
                expired.append(key)
            else:
                live.append(key)
        for key in expired:
            del self._data[key]
        return live

    def size(self) -> int:
        return len(self.keys())

    def clear(self) -> None:
        self._data.clear()
