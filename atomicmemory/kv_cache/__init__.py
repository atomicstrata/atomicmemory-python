"""Local key/value cache adapters — in-memory + SQLite.

Port of the kv-cache layer in `atomicmemory-sdk/src/kv-cache/`. The
``StorageAdapter`` Protocol is the contract every adapter satisfies;
two concrete implementations ship with the SDK:

- :class:`MemoryStorageAdapter` — pure-Python dict-backed store, useful
  for tests and short-lived agent runs.
- :class:`SQLiteStorageAdapter` — stdlib ``sqlite3``-backed store with
  TTL support, suitable for local persistence in CLIs and notebooks.
"""

from atomicmemory.kv_cache.adapter import StorageAdapter
from atomicmemory.kv_cache.memory_storage import MemoryStorageAdapter
from atomicmemory.kv_cache.sqlite_storage import SQLiteStorageAdapter

__all__ = ["MemoryStorageAdapter", "SQLiteStorageAdapter", "StorageAdapter"]
