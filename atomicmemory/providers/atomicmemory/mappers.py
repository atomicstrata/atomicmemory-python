"""Wire-format ↔ V3 type mappers for the AtomicMemory provider.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/mappers.ts`.
Field-for-field equivalent. Date strings are parsed with
``datetime.fromisoformat`` (handles both ``+00:00`` and ``Z`` in 3.11+
via the small normalization helper below).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atomicmemory.memory.types import (
    IngestResult,
    Memory,
    MemoryVersion,
    MemoryVersionEvent,
    Provenance,
    Scope,
    SearchResult,
)

_AUDIT_EVENTS: set[MemoryVersionEvent] = {"created", "updated", "superseded", "invalidated"}


def _coalesce(*values: Any) -> Any:
    """Return the first value that is not None.

    Python equivalent of TS's ``??`` (nullish coalescing). Crucial for
    score fields where ``0.0`` is a legitimate value: ``a or b`` would
    incorrectly treat ``0.0`` as missing.
    """
    for value in values:
        if value is not None:
            return value
    return None


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime, normalizing trailing 'Z' to UTC."""
    if value is None:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def to_memory(raw: dict[str, Any], scope: Scope) -> Memory:
    """Map a single core memory record to a V3 ``Memory``."""
    created_at = _parse_iso(raw.get("created_at")) or datetime.now(tz=timezone.utc)
    return Memory(
        id=raw["id"],
        content=raw["content"],
        scope=_build_scope(raw, scope),
        created_at=created_at,
        provenance=_build_provenance(raw),
        metadata=_build_metadata(raw),
    )


def _build_scope(raw: dict[str, Any], scope: Scope) -> Scope:
    """Merge backend-projected scope fields and validate scoped reads."""
    namespace = raw.get("namespace")
    session_id = raw.get("session_id")
    if scope.namespace is not None and namespace is not None and namespace != scope.namespace:
        raise ValueError("atomicmemory provider: backend response `namespace` did not match requested namespace scope")
    if scope.thread is not None:
        if not session_id:
            raise ValueError(
                "atomicmemory provider: backend response missing required `session_id` for thread-scoped request"
            )
        if session_id != scope.thread:
            raise ValueError(
                "atomicmemory provider: backend response `session_id` did not match requested thread scope"
            )

    updates: dict[str, Any] = {}
    if namespace:
        updates["namespace"] = namespace
    if session_id:
        updates["thread"] = session_id
    return scope.model_copy(update=updates)


def _build_provenance(raw: dict[str, Any]) -> Provenance | None:
    fields: dict[str, Any] = {}
    if "source_site" in raw and raw["source_site"] is not None:
        fields["source"] = raw["source_site"]
    if "source_url" in raw and raw["source_url"] is not None:
        fields["source_url"] = raw["source_url"]
    if not fields:
        return None
    return Provenance(**fields)


def _build_metadata(raw: dict[str, Any]) -> dict[str, Any] | None:
    metadata: dict[str, Any] = {}
    if "importance" in raw and raw["importance"] is not None:
        metadata["importance"] = raw["importance"]
    if "episode_id" in raw and raw["episode_id"] is not None:
        metadata["episode_id"] = raw["episode_id"]
    return metadata or None


def to_search_result(raw: dict[str, Any], scope: Scope) -> SearchResult:
    """Map a single search hit, preserving every score variant core emits.

    Mirrors TS's ``??`` semantics so that legitimate ``0.0`` scores are
    not silently replaced by a fallback field.
    """
    similarity = _coalesce(raw.get("semantic_similarity"), raw.get("similarity"))
    ranking_score = _coalesce(raw.get("ranking_score"), raw.get("score"))
    relevance = raw.get("relevance")
    score = _coalesce(ranking_score, similarity, 0.0)
    return SearchResult(
        memory=to_memory(raw, scope),
        score=score,
        similarity=similarity,
        ranking_score=ranking_score,
        relevance=relevance,
    )


def to_ingest_result(raw: dict[str, Any]) -> IngestResult:
    """Map ``POST /memories/ingest[/quick]`` response to V3 IngestResult."""
    return IngestResult(
        created=list(raw.get("stored_memory_ids") or []),
        updated=list(raw.get("updated_memory_ids") or []),
        unchanged=[],
    )


def to_memory_version(raw: dict[str, Any]) -> MemoryVersion:
    """Map an audit-trail entry to a V3 ``MemoryVersion``.

    Unknown ``event`` values are normalized to ``"created"`` (matches TS).
    """
    raw_event = raw.get("event")
    event: MemoryVersionEvent = raw_event if raw_event in _AUDIT_EVENTS else "created"
    created_at = _parse_iso(raw.get("created_at"))
    if created_at is None:
        raise ValueError("audit entry missing created_at")
    return MemoryVersion(
        id=raw["id"],
        content=raw["content"],
        created_at=created_at,
        parent_id=raw.get("parent_id"),
        event=event,
    )
