"""SQLite-backed storage adapter.

Stdlib-only — no SQLAlchemy. Stores values as JSON text. TTL is enforced
on read (lazy eviction); a periodic ``vacuum_expired`` helper is
provided for callers that want eager cleanup.

The TTL clock defaults to :func:`time.time` (wall-clock epoch seconds)
so persisted ``expires_at`` values remain meaningful across process
restarts. Tests can inject a deterministic ``clock=`` callable.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from atomicmemory.core.errors import ConfigError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS atomicmemory_kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL
);
"""


class SQLiteStorageAdapter:
    """SQLite-backed key/value store with optional TTL."""

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._clock: Callable[[], float] = clock or time.time

    def initialize(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.execute(_SCHEMA)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteStorageAdapter is not initialized; call initialize() first.")
        return self._conn

    def get(self, key: str) -> Any | None:
        row = self._require().execute("SELECT value, expires_at FROM atomicmemory_kv WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        value_text, expires_at = row
        if expires_at is not None and self._clock() >= expires_at:
            self.delete(key)
            return None
        return json.loads(value_text)

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
                "SQLiteStorageAdapter does not implement encryption; "
                "passing encrypt=True would silently store plaintext. "
                "Omit the flag or use a backend that implements ciphered storage.",
                context={"adapter": "SQLiteStorageAdapter"},
            )
        now = self._clock()
        expires_at = now + ttl_seconds if ttl_seconds is not None else None
        self._require().execute(
            "INSERT INTO atomicmemory_kv(key, value, created_at, expires_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value=excluded.value, created_at=excluded.created_at, expires_at=excluded.expires_at",
            (key, json.dumps(value), now, expires_at),
        )

    def delete(self, key: str) -> bool:
        cursor = self._require().execute("DELETE FROM atomicmemory_kv WHERE key = ?", (key,))
        return (cursor.rowcount or 0) > 0

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self) -> list[str]:
        self.vacuum_expired()
        rows = self._require().execute("SELECT key FROM atomicmemory_kv ORDER BY key").fetchall()
        return [row[0] for row in rows]

    def size(self) -> int:
        self.vacuum_expired()
        row = self._require().execute("SELECT COUNT(*) FROM atomicmemory_kv").fetchone()
        return int(row[0]) if row is not None else 0

    def clear(self) -> None:
        self._require().execute("DELETE FROM atomicmemory_kv")

    def vacuum_expired(self) -> int:
        """Delete rows whose ``expires_at`` is in the past. Returns the row count deleted."""
        now = self._clock()
        cursor = self._require().execute(
            "DELETE FROM atomicmemory_kv WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        return cursor.rowcount or 0
