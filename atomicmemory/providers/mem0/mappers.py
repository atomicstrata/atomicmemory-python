"""Wire-format mappers + body builders for the Mem0 provider.

Port of `atomicmemory-sdk/src/memory/mem0-provider/mappers.ts`. Pure
functions — shared by the sync and async providers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from atomicmemory.memory.types import (
    IngestInput,
    IngestResult,
    Memory,
    Scope,
    SearchResult,
)
from atomicmemory.providers.mem0.config import Mem0ProviderConfig

_MetadataDict = dict[str, Any]


def unwrap_mem0_array(raw: Any) -> list[_MetadataDict]:
    """Return a list of memory dicts from either a bare array or ``{results: [...]}``."""
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, dict) and "results" in raw:
        results = raw["results"]
        if isinstance(results, list):
            return list(results)
    return []


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def _extract_memory_text(raw: dict[str, Any]) -> str:
    """Pick the memory text from either flat ``memory`` or nested ``data.memory``."""
    if raw.get("memory") is not None:
        return str(raw["memory"])
    data = raw.get("data")
    if isinstance(data, dict) and data.get("memory") is not None:
        return str(data["memory"])
    return ""


def to_memory(raw: dict[str, Any], scope: Scope) -> Memory:
    return Memory(
        id=str(raw["id"]),
        content=_extract_memory_text(raw),
        scope=scope,
        created_at=_parse_iso(raw.get("created_at")) or datetime.now().astimezone(),
        updated_at=_parse_iso(raw.get("updated_at")),
        metadata=raw.get("metadata"),
    )


def to_search_result(raw: dict[str, Any], scope: Scope) -> SearchResult:
    raw_score = raw.get("score")
    score: float = float(raw_score) if raw_score is not None else 0.0
    return SearchResult(memory=to_memory(raw, scope), score=score)


def to_ingest_result(raw_memories: list[dict[str, Any]]) -> IngestResult:
    created: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    for mem in raw_memories:
        event = (mem.get("event") or "ADD").upper()
        if event == "ADD":
            created.append(str(mem.get("id", "")))
        elif event == "UPDATE":
            updated.append(str(mem.get("id", "")))
        elif event in {"NONE", "NOOP"}:
            unchanged.append(str(mem.get("id", "")))
        else:
            created.append(str(mem.get("id", "")))
    return IngestResult(created=created, updated=updated, unchanged=unchanged)


def resolve_infer_flag(input: IngestInput, config: Mem0ProviderConfig) -> bool:
    metadata = input.metadata or {}
    metadata_infer = metadata.get("infer") if isinstance(metadata, dict) else None
    if isinstance(metadata_infer, bool):
        return metadata_infer
    return config.default_infer


def build_ingest_body(input: IngestInput, user_id: str, config: Mem0ProviderConfig) -> dict[str, Any]:
    """Compose Mem0's ``POST /v1/memories/`` request body."""
    metadata = input.metadata or {}
    clean_metadata = {k: v for k, v in metadata.items() if k != "infer"} if isinstance(metadata, dict) else {}
    body: dict[str, Any] = {
        "user_id": user_id,
        "infer": resolve_infer_flag(input, config),
    }
    if clean_metadata:
        body["metadata"] = clean_metadata
    if input.mode == "text":
        body["messages"] = [{"role": "user", "content": input.content}]
    elif input.mode == "messages":
        body["messages"] = [{"role": m.role, "content": m.content} for m in input.messages]
    _apply_enterprise_fields(body, config)
    _apply_scope_identifiers(body, input.scope)
    return body


def build_search_body(
    query: str,
    scope: Scope,
    config: Mem0ProviderConfig,
    limit: int | None = None,
) -> dict[str, Any]:
    """Compose Mem0 v2's ``POST /v2/memories/search/`` body with nested filters."""
    filters: dict[str, Any] = {}
    if scope.user:
        filters["user_id"] = scope.user
    if scope.agent:
        filters["agent_id"] = scope.agent
    if scope.thread:
        filters["run_id"] = scope.thread
    body: dict[str, Any] = {"query": query, "filters": filters}
    if limit is not None:
        body["limit"] = limit
    _apply_enterprise_fields(body, config)
    return body


def _apply_enterprise_fields(body: dict[str, Any], config: Mem0ProviderConfig) -> None:
    if config.org_id:
        body["org_id"] = config.org_id
    if config.project_id:
        body["project_id"] = config.project_id


def _apply_scope_identifiers(body: dict[str, Any], scope: Scope) -> None:
    if scope.agent:
        body["agent_id"] = scope.agent
    if scope.thread:
        body["run_id"] = scope.thread
