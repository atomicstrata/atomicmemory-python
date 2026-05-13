"""Tests for V3 memory types (Pydantic models + discriminated unions)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from atomicmemory.memory.types import (
    IngestInput,
    Memory,
    MessageIngest,
    Scope,
    SearchRequest,
    TextIngest,
    VerbatimIngest,
)

_INGEST_ADAPTER: TypeAdapter[IngestInput] = TypeAdapter(IngestInput)


def test_scope_accepts_partial_fields() -> None:
    scope = Scope(user="u1")

    assert scope.user == "u1"
    assert scope.agent is None
    assert scope.namespace is None


def test_scope_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Scope.model_validate({"user": "u1", "foo": "bar"})


def test_memory_parses_iso_datetime() -> None:
    m = Memory.model_validate(
        {
            "id": "m1",
            "content": "hi",
            "scope": {"user": "u1"},
            "created_at": "2024-01-01T12:00:00Z",
        }
    )

    assert isinstance(m.created_at, datetime)
    assert m.created_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_ingest_discriminator_picks_text_variant() -> None:
    parsed = _INGEST_ADAPTER.validate_python({"mode": "text", "content": "hi", "scope": {"user": "u"}})
    assert isinstance(parsed, TextIngest)
    assert parsed.content == "hi"


def test_ingest_discriminator_picks_messages_variant() -> None:
    parsed = _INGEST_ADAPTER.validate_python(
        {
            "mode": "messages",
            "messages": [{"role": "user", "content": "hi"}],
            "scope": {"user": "u"},
        }
    )
    assert isinstance(parsed, MessageIngest)
    assert parsed.messages[0].role == "user"


def test_ingest_discriminator_picks_verbatim_variant() -> None:
    parsed = _INGEST_ADAPTER.validate_python({"mode": "verbatim", "content": "saved as-is", "scope": {"user": "u"}})
    assert isinstance(parsed, VerbatimIngest)


def test_ingest_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        _INGEST_ADAPTER.validate_python({"mode": "unknown", "scope": {"user": "u"}})


def test_search_request_accepts_filter_and_threshold() -> None:
    req = SearchRequest.model_validate({"query": "hi", "scope": {"user": "u"}, "limit": 5, "threshold": 0.2})

    assert req.query == "hi"
    assert req.limit == 5
    assert req.threshold == 0.2


def test_search_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "hi", "scope": {"user": "u"}, "bogus": True})
