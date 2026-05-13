"""StorageAdapter protocol — common contract for local key/value caches.

Port of `atomicmemory-sdk/src/kv-cache/storage-adapter.ts`. The methods
mirror the TS surface, with snake_case naming.

Encryption is **not** implemented in any shipped adapter. The
``encrypt`` keyword on :meth:`set` exists for forward compatibility
with future ciphered backends, but concrete adapters MUST fail closed:
when a caller passes ``encrypt=True``, a conformant implementation
raises :class:`atomicmemory.core.errors.ConfigError` rather than
silently storing plaintext under a flag that signals confidentiality.
:class:`MemoryStorageAdapter` and :class:`SQLiteStorageAdapter` follow
that contract today; new adapters must too until real encryption lands.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class StorageAdapter(Protocol):
    """Common storage contract — get/set/delete/keys + TTL + size."""

    def initialize(self) -> None: ...

    def close(self) -> None: ...

    def get(self, key: str) -> Any | None: ...

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: float | None = None,
        encrypt: bool = False,
    ) -> None: ...

    def delete(self, key: str) -> bool: ...

    def has(self, key: str) -> bool: ...

    def keys(self) -> list[str]: ...

    def size(self) -> int: ...

    def clear(self) -> None: ...
