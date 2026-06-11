"""Unit tests for the atomicmemory.contract.v1 wire codec.

Each test exercises a specific codec boundary: camel↔snake field renames,
``_to_iso_z`` millisecond precision, provenance nesting in Memory and ingest,
``rankingScore`` mapping, page round-trip, datetime-filter normalization, and
the ``content_class`` rejection guard.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from atomicmemory.contract import v1
from atomicmemory.memory.filters import FilterExpr
from atomicmemory.memory.types import (
    Memory,
    Provenance,
    Scope,
    SearchRequest,
    SearchResultPage,
    VerbatimIngest,
)

_WIRE_MEMORY = {
    "id": "mem_1",
    "content": "hello",
    "scope": {"user": "u1"},
    "kind": "fact",
    "createdAt": "2026-05-30T12:00:00.000Z",
}


def test_decode_memory_maps_camel_dates() -> None:
    memory = v1.decode_memory(_WIRE_MEMORY)
    assert memory.created_at == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    assert memory.updated_at is None


def test_encode_memory_round_trips_to_exact_wire_form() -> None:
    memory = v1.decode_memory(_WIRE_MEMORY)
    assert v1.encode_memory(memory) == _WIRE_MEMORY


def test_encode_memory_emits_toISOString_format() -> None:
    memory = Memory(
        id="m",
        content="c",
        scope=Scope(user="u"),
        created_at=datetime(2026, 5, 30, 12, 0, 0, 123456, tzinfo=timezone.utc),
    )
    assert v1.encode_memory(memory)["createdAt"] == "2026-05-30T12:00:00.123Z"


def test_encode_memory_treats_naive_datetime_as_utc() -> None:
    # Regression: astimezone() on a NAIVE datetime assumes LOCAL system time,
    # so without an explicit UTC default a naive noon shifts by the host's
    # UTC offset (e.g. emits 19:00Z on a UTC-7 machine).
    memory = Memory(id="m", content="c", scope=Scope(user="u"), created_at=datetime(2026, 5, 30, 12, 0, 0))
    assert v1.encode_memory(memory)["createdAt"] == "2026-05-30T12:00:00.000Z"


def test_decode_memory_rejects_missing_created_at() -> None:
    bad = {k: v for k, v in _WIRE_MEMORY.items() if k != "createdAt"}
    with pytest.raises(PydanticValidationError):
        v1.decode_memory(bad)


def test_search_result_page_round_trip() -> None:
    page_wire = {
        "results": [
            {
                "memory": _WIRE_MEMORY,
                "score": 0.9,
                "rankingScore": 0.42,
                "version_id": "v1",
                "observed_at": "2026-05-30T12:00:00.000Z",
            }
        ],
        "retrieval": {
            "embedding_model": "m",
            "embedding_model_version": "1",
            "embedding_dimensions": 8,
            "query_text": "q",
            "candidate_ids": ["mem_1"],
            "trace_id": "t",
        },
    }
    page = v1.decode_search_result_page(page_wire)
    assert isinstance(page, SearchResultPage)
    assert page.results[0].memory.created_at.tzinfo is not None
    assert page.results[0].ranking_score == 0.42  # rankingScore camel↔snake pinned
    assert v1.encode_search_result_page(page) == page_wire


def test_provenance_camel_fields_round_trip_in_memory_and_ingest() -> None:
    wire_prov = {"source": "app", "sourceUrl": "https://x.test/d", "sourceId": "doc-1"}
    memory = v1.decode_memory({**_WIRE_MEMORY, "provenance": wire_prov})
    assert memory.provenance is not None and memory.provenance.source_url == "https://x.test/d"
    assert v1.encode_memory(memory)["provenance"] == wire_prov


def test_encode_search_request_normalizes_datetimes_in_nested_filters() -> None:
    # NESTED (an `and` wrapper, not just a leaf): proves both the recursive
    # datetime walk AND the by_alias dump (a non-alias dump emits "and_",
    # which the schema rejects).
    stamp = datetime(2026, 5, 30, 12, 0, 0, 123456, tzinfo=timezone.utc)
    request = SearchRequest(
        query="q",
        scope=Scope(user="u"),
        filter=FilterExpr.model_validate(
            {
                "and": [
                    {"field": "createdAt", "op": "gte", "value": stamp},
                    {"field": "kind", "op": "eq", "value": "fact"},
                ]
            }
        ),
    )
    encoded = v1.encode_search_request(request)
    assert "and" in encoded["filter"] and "and_" not in encoded["filter"]
    assert encoded["filter"]["and"][0]["value"] == "2026-05-30T12:00:00.123Z"


def test_ingest_provenance_camel_fields_round_trip() -> None:
    # Provenance nests in every ingest mode — the corpus never carries
    # sourceUrl/sourceId, so this synthetic case is the only coverage.
    wire_provenance = {"source": "app", "sourceUrl": "https://x.test/d", "sourceId": "doc-1"}
    text_ingest = VerbatimIngest(
        content="hello",
        scope=Scope(user="u1"),
        provenance=Provenance(source="app", source_url="https://x.test/d", source_id="doc-1"),
    )
    emitted = v1.encode_ingest_input(text_ingest)
    assert emitted["provenance"] == wire_provenance


def test_metadata_datetimes_encode_in_wire_date_form() -> None:
    # metadata is schema-open (additionalProperties: true) but CONTRACT.md §1's
    # date rule still applies to any datetime that crosses the boundary — and
    # the json-mode dump would emit the wrong (seconds-precision) form.
    stamp = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
    memory = Memory(
        id="m",
        content="c",
        scope=Scope(user="u"),
        created_at=stamp,
        metadata={"event_at": stamp},
    )
    assert v1.encode_memory(memory)["metadata"]["event_at"] == "2026-05-30T12:00:00.000Z"
    ingest = VerbatimIngest(content="c", scope=Scope(user="u"), metadata={"event_at": stamp})
    assert v1.encode_ingest_input(ingest)["metadata"]["event_at"] == "2026-05-30T12:00:00.000Z"


def test_decoded_null_version_id_normalizes_to_absent_on_encode() -> None:
    # TS pins `versionId?: string | null` (OPTIONAL nullable; types.ts @
    # 2a67871): absent and null are both valid wire forms of the None state,
    # and the codec re-encodes the optional field in its canonical absent form.
    result = v1.decode_search_result({"memory": _WIRE_MEMORY, "score": 0.5, "version_id": None})
    assert result.version_id is None
    assert "version_id" not in v1.encode_search_result(result)


def test_encode_ingest_input_rejects_python_only_content_class() -> None:
    model = VerbatimIngest(content="x", scope=Scope(user="u"), content_class="summary")
    with pytest.raises(ValueError, match="content_class"):
        v1.encode_ingest_input(model)


def test_decode_memory_rejects_in_process_snake_date_key() -> None:
    # The codec is a STRICT v1 boundary: in-process snake names are not wire
    # names, and the rename-if-present pattern must not let them through.
    bad = {k: v for k, v in _WIRE_MEMORY.items() if k != "createdAt"}
    bad["created_at"] = "2026-05-30T12:00:00.000Z"
    with pytest.raises(ValueError, match="non-v1 wire keys"):
        v1.decode_memory(bad)


def test_decode_search_result_rejects_in_process_snake_score_key() -> None:
    with pytest.raises(ValueError, match="non-v1 wire keys"):
        v1.decode_search_result({"memory": _WIRE_MEMORY, "score": 0.5, "ranking_score": 0.42})


def test_decode_provenance_rejects_in_process_snake_url_key() -> None:
    with pytest.raises(ValueError, match="non-v1 wire keys"):
        v1.decode_provenance({"source": "app", "source_url": "https://x.test/d"})


def test_decode_search_result_page_rejects_unknown_extra_key() -> None:
    # The schemas declare additionalProperties: false; extra="ignore" models
    # would silently drop unknown keys without the wire-key guard.
    with pytest.raises(ValueError, match="non-v1 wire keys"):
        v1.decode_search_result_page({"results": [], "extra": 1})


def test_decode_search_request_is_passthrough() -> None:
    # SearchRequest is fully snake_case on the wire; decode is a thin
    # model_validate passthrough — pinned so an accidental alias rename
    # in the codec can't go undetected (the only previously-untested
    # public codec function).
    wire = {"query": "deploy gate", "scope": {"user": "u1"}, "limit": 5}
    model = v1.decode_search_request(wire)
    assert model.query == "deploy gate"
    assert model.limit == 5
    assert model.scope.user == "u1"
