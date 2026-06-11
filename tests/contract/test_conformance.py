"""Two-direction conformance harness over the vendored v1 corpus.

Direction 1 (wire → SDK): every corpus request/response decodes into the
Python models — directly for the snake-on-wire types, through the
``atomicmemory.contract.v1`` codec for the mixed-case search response.
Direction 2 (SDK → wire): the decoded models re-encode to payloads that
validate against the vendored JSON Schemas.
Plus the TS suite's negative cases, mirrored against schema AND Pydantic.

The capabilities-descriptor case is schema-only: its expected_response is the
wire-level capability descriptor, which the Python SDK has no model for yet —
a recorded program follow-up (the Python ``Capabilities`` model is the
in-process surface; the over-the-wire ``capabilities-descriptor.schema.json``
shape has no Python counterpart in this PR).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from atomicmemory.contract import v1 as codec
from atomicmemory.memory.types import (
    IngestInput,
    IngestResult,
    RetrievalReceipt,
    SearchRequest,
)
from tests.contract._schema_registry import validator_for

V1_DIR = Path(__file__).resolve().parents[2] / "contract" / "v1"
_CASES = {
    c["name"]: json.loads((V1_DIR / "conformance" / c["file"]).read_text())
    for c in json.loads((V1_DIR / "conformance" / "manifest.json").read_text())["cases"]
}
_INGEST: TypeAdapter[IngestInput] = TypeAdapter(IngestInput)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_corpus_payloads_validate_against_schemas(name: str) -> None:
    """Every corpus request and response validates against its declared schema."""
    case = _CASES[name]
    assert "response_schema" in case and "expected_response" in case, (
        f"corpus case {name!r} is missing response_schema or expected_response"
    )
    if case.get("request_schema") and case.get("request") is not None:
        validator_for(case["request_schema"]).validate(case["request"])
    validator_for(case["response_schema"]).validate(case["expected_response"])


def test_ingest_cases_round_trip_through_models() -> None:
    """Ingest corpus cases decode through the TypeAdapter and re-encode schema-valid."""
    # Derived from the corpus, not hard-coded names: a refresh that ADDS an
    # ingest case must not be silently under-tested, and a rename must fail
    # actionably. The count pin mirrors the manifest-level len==4 philosophy.
    ingest_cases = [c for c in _CASES.values() if c["operation"] == "ingest"]
    assert len(ingest_cases) == 2, (
        f"expected 2 ingest corpus cases, got {[c['name'] for c in ingest_cases]} — "
        "a corpus refresh changed the ingest set; extend this round-trip accordingly"
    )
    for case in ingest_cases:
        model = _INGEST.validate_python(case["request"])
        encoded = codec.encode_ingest_input(model)
        validator_for(case["request_schema"]).validate(encoded)
        result = codec.decode_ingest_result(case["expected_response"])
        assert isinstance(result, IngestResult)


def test_search_request_round_trips() -> None:
    """Search corpus request decodes through SearchRequest and re-encodes schema-valid."""
    # Through the codec, not raw model_dump: the corpus request happens to be
    # filter-free, but encode_search_request is the v1 surface (it normalizes
    # datetime filter operands to toISOString form) — exercise the real path.
    case = _CASES["search-with-retrieval-receipt"]
    model = SearchRequest.model_validate(case["request"])
    encoded = codec.encode_search_request(model)
    validator_for(case["request_schema"]).validate(encoded)


def test_format_keyword_is_enforced_not_advisory() -> None:
    """A malformed date-time string is rejected by the FormatChecker-backed validator."""
    # Without a FormatChecker, jsonschema treats format: date-time as advisory
    # and "not-a-date" would validate — pin that our validators enforce it.
    case = _CASES["search-with-retrieval-receipt"]
    page = json.loads(json.dumps(case["expected_response"]))
    page["results"][0]["memory"]["createdAt"] = "not-a-date"
    assert not validator_for(case["response_schema"]).is_valid(page)


def test_search_response_round_trips_through_the_codec() -> None:
    """The decisive parity test: search response decodes via codec and re-encodes byte-equal."""
    # The mixed-case wire page decodes into the in-process models via the codec,
    # and re-encodes to a schema-valid, byte-equal wire form.
    case = _CASES["search-with-retrieval-receipt"]
    page = codec.decode_search_result_page(case["expected_response"])
    encoded = codec.encode_search_result_page(page)
    validator_for(case["response_schema"]).validate(encoded)
    assert encoded == case["expected_response"]


def test_unknown_ingest_mode_rejected_by_both_validators() -> None:
    """An unknown mode value is rejected by both the schema and the Pydantic discriminator."""
    bad = dict(_CASES["ingest-text"]["request"], mode="binary")
    assert not validator_for(_CASES["ingest-text"]["request_schema"]).is_valid(bad)
    with pytest.raises(PydanticValidationError):
        _INGEST.validate_python(bad)


def test_codec_wire_key_sets_match_the_vendored_schemas() -> None:
    """The codec's hard-coded wire-key sets stay in lockstep with the schemas."""
    # The key sets are code literals (the wheel doesn't ship contract/), so a
    # schema refresh that adds/renames a property must fail here, forcing a
    # conscious codec update. All five $defs declare additionalProperties:
    # false, which is what licenses the strict decode guard.
    contract = json.loads((V1_DIR / "provider-contract.schema.json").read_text())
    defs = contract["$defs"]
    expectations = {
        "Memory": codec._MEMORY_WIRE_KEYS,
        "Provenance": codec._PROVENANCE_WIRE_KEYS,
        "SearchResult": codec._SEARCH_RESULT_WIRE_KEYS,
        "SearchResultPage": codec._SEARCH_RESULT_PAGE_WIRE_KEYS,
        "IngestResult": codec._INGEST_RESULT_WIRE_KEYS,
    }
    for def_name, wire_keys in expectations.items():
        assert defs[def_name].get("additionalProperties") is False, (
            f"{def_name} no longer declares additionalProperties: false — "
            "re-evaluate whether the strict decode guard is still licensed"
        )
        assert set(defs[def_name]["properties"]) == set(wire_keys), def_name


def test_receipt_missing_trace_id_rejected_by_both_validators() -> None:
    """A retrieval receipt missing trace_id is rejected by both the schema and Pydantic."""
    page = json.loads(json.dumps(_CASES["search-with-retrieval-receipt"]["expected_response"]))
    del page["retrieval"]["trace_id"]
    assert not validator_for(_CASES["search-with-retrieval-receipt"]["response_schema"]).is_valid(page)
    with pytest.raises(PydanticValidationError):
        RetrievalReceipt.model_validate(page["retrieval"])
