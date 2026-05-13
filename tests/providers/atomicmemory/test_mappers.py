"""Tests for wire-format ↔ V3 mappers (snake_case in / Pydantic out)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from atomicmemory.memory.types import Scope
from atomicmemory.providers.atomicmemory.mappers import (
    to_ingest_result,
    to_memory,
    to_memory_version,
    to_search_result,
)

_SCOPE = Scope(user="u1")


def test_to_memory_parses_iso_timestamp_with_z() -> None:
    raw = {"id": "m1", "content": "hi", "created_at": "2024-01-01T12:00:00Z"}

    memory = to_memory(raw, _SCOPE)

    assert memory.id == "m1"
    assert memory.content == "hi"
    assert memory.scope == _SCOPE
    assert memory.created_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_to_memory_builds_provenance_only_when_fields_present() -> None:
    raw = {"id": "m1", "content": "hi", "source_site": "chat", "source_url": "https://x"}

    memory = to_memory(raw, _SCOPE)

    assert memory.provenance is not None
    assert memory.provenance.source == "chat"
    assert memory.provenance.source_url == "https://x"


def test_to_memory_omits_provenance_when_no_fields() -> None:
    memory = to_memory({"id": "m1", "content": "hi"}, _SCOPE)
    assert memory.provenance is None


def test_to_memory_metadata_preserves_zero_importance() -> None:
    memory = to_memory({"id": "m1", "content": "hi", "importance": 0}, _SCOPE)
    assert memory.metadata == {"importance": 0}


def test_to_memory_includes_episode_id_in_metadata() -> None:
    memory = to_memory({"id": "m1", "content": "hi", "episode_id": "ep-1"}, _SCOPE)
    assert memory.metadata == {"episode_id": "ep-1"}


def test_to_search_result_prefers_semantic_similarity() -> None:
    raw = {"id": "m1", "content": "hi", "semantic_similarity": 0.9, "similarity": 0.5, "score": 0.7}

    result = to_search_result(raw, _SCOPE)

    assert result.similarity == 0.9
    assert result.ranking_score == 0.7
    assert result.score == 0.7


def test_to_search_result_falls_back_to_similarity_when_no_score() -> None:
    raw = {"id": "m1", "content": "hi", "similarity": 0.4}

    result = to_search_result(raw, _SCOPE)

    assert result.similarity == 0.4
    assert result.score == 0.4


def test_to_search_result_preserves_zero_similarity() -> None:
    """0.0 is a legitimate score; must not be coalesced to fallback or default."""
    raw = {"id": "m1", "content": "hi", "semantic_similarity": 0.0, "similarity": 0.7}

    result = to_search_result(raw, _SCOPE)

    assert result.similarity == 0.0
    assert result.score == 0.0


def test_to_search_result_preserves_zero_ranking_score() -> None:
    raw = {"id": "m1", "content": "hi", "ranking_score": 0.0, "score": 0.5}

    result = to_search_result(raw, _SCOPE)

    assert result.ranking_score == 0.0
    assert result.score == 0.0


def test_to_ingest_result_splits_created_and_updated() -> None:
    raw = {
        "stored_memory_ids": ["m1", "m2"],
        "updated_memory_ids": ["m3"],
        "memories_skipped": 5,
    }

    result = to_ingest_result(raw)

    assert result.created == ["m1", "m2"]
    assert result.updated == ["m3"]
    assert result.unchanged == []


def test_to_memory_version_normalizes_unknown_event() -> None:
    raw = {
        "id": "v1",
        "content": "hi",
        "created_at": "2024-01-01T00:00:00Z",
        "event": "weird-event",
    }

    version = to_memory_version(raw)

    assert version.event == "created"


def test_to_memory_version_requires_created_at() -> None:
    with pytest.raises(ValueError, match="created_at"):
        to_memory_version({"id": "v1", "content": "hi"})
