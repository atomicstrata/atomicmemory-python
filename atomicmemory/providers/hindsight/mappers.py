"""Hindsight request builders and strict response mappers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from atomicmemory.memory.types import IngestInput, Memory, MemoryKind, Message, Scope, SearchResult
from atomicmemory.providers.hindsight.config import (
    HINDSIGHT_DEFAULT_MAX_TOKENS,
    HINDSIGHT_SCOPE_TAGS_MATCH,
    HindsightProviderConfig,
)


def bank_id_for_scope(scope: Scope) -> str:
    return scope.user or ""


def tags_for_scope(scope: Scope) -> list[str]:
    tags: list[str] = []
    if scope.agent:
        tags.append(f"agent:{scope.agent}")
    if scope.namespace:
        tags.append(f"namespace:{scope.namespace}")
    if scope.thread:
        tags.append(f"thread:{scope.thread}")
    return tags


def build_retain_request(input: IngestInput) -> dict[str, Any]:
    return {"items": [_build_retain_item(input)], "async": False}


def build_recall_request(
    query: str,
    scope: Scope,
    config: HindsightProviderConfig,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    tags = tags_for_scope(scope)
    body: dict[str, Any] = {
        "query": query,
        "max_tokens": max_tokens
        if max_tokens is not None
        else config.default_max_tokens or HINDSIGHT_DEFAULT_MAX_TOKENS,
    }
    if config.default_budget:
        body["budget"] = config.default_budget
    if tags:
        body["tags"] = tags
        body["tags_match"] = HINDSIGHT_SCOPE_TAGS_MATCH
    return body


def build_reflect_request(query: str, scope: Scope) -> dict[str, Any]:
    tags = tags_for_scope(scope)
    body: dict[str, Any] = {"query": query}
    if tags:
        body["tags"] = tags
        body["tags_match"] = HINDSIGHT_SCOPE_TAGS_MATCH
    return body


def unwrap_results(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        raise ValueError("Hindsight recall response missing results array")
    return list(raw["results"])


def to_memory(raw: dict[str, Any], scope: Scope) -> Memory:
    memory_id = _require_string(raw.get("id"), "id")
    return Memory(
        id=memory_id,
        content=_require_string(raw.get("text"), f"text for memory {memory_id}"),
        scope=scope,
        kind=_map_memory_kind(raw.get("type")),
        created_at=_parse_memory_date(raw),
        updated_at=_parse_iso(raw.get("updated_at")),
        metadata=_build_metadata(raw),
    )


def to_search_result(raw: dict[str, Any], scope: Scope) -> SearchResult:
    return SearchResult(memory=to_memory(raw, scope), score=0.0)


def messages_to_transcript(messages: list[Message]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def estimate_tokens(text: str) -> int:
    if text == "":
        return 0
    return (len(text) + 3) // 4


def _build_retain_item(input: IngestInput) -> dict[str, Any]:
    metadata = _build_ingest_metadata(input)
    item: dict[str, Any] = {
        "content": messages_to_transcript(input.messages) if input.mode == "messages" else input.content,
        "tags": tags_for_scope(input.scope),
    }
    if input.provenance and input.provenance.source:
        item["context"] = input.provenance.source
    if metadata:
        item["metadata"] = metadata
    return item


def _build_ingest_metadata(input: IngestInput) -> dict[str, Any]:
    metadata = dict(input.metadata or {})
    if input.provenance is None:
        return metadata
    if input.provenance.source:
        metadata["source"] = input.provenance.source
    if input.provenance.source_url:
        metadata["sourceUrl"] = input.provenance.source_url
    if input.provenance.source_id:
        metadata["sourceId"] = input.provenance.source_id
    return metadata


def _build_metadata(raw: dict[str, Any]) -> dict[str, Any] | None:
    metadata = dict(raw["metadata"]) if isinstance(raw.get("metadata"), dict) else {}
    for source, target in _METADATA_FIELDS.items():
        if raw.get(source) is not None:
            metadata[target] = raw[source]
    return metadata or None


_METADATA_FIELDS = {
    "type": "hindsightType",
    "context": "context",
    "tags": "tags",
    "entities": "entities",
    "occurred_start": "occurredStart",
    "occurred_end": "occurredEnd",
    "mentioned_at": "mentionedAt",
    "date": "hindsightDate",
}


def _map_memory_kind(raw_type: Any) -> MemoryKind | None:
    if raw_type == "world":
        return "fact"
    if raw_type == "experience":
        return "episode"
    if raw_type == "observation":
        return "summary"
    return None


def _parse_memory_date(raw: dict[str, Any]) -> datetime:
    value = raw.get("created_at") or raw.get("mentioned_at") or raw.get("date")
    if isinstance(value, str) and value:
        parsed = _parse_iso(value)
        if parsed is not None:
            return parsed
    raise ValueError(f"Hindsight memory {raw.get('id') or '<unknown>'} missing timestamp field")


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def _require_string(value: Any, field: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Hindsight response missing required {field}")
