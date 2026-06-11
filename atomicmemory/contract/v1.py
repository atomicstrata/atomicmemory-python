"""v1 provider-contract wire codec.

Translates between the idiomatic snake_case in-process models and the v1 wire
encoding pinned by ``contract/CONTRACT.md`` + ``contract/v1/*.schema.json``.
The wire casing is deliberately mixed (``Memory.createdAt`` camel;
``version_id``/receipt fields snake); this module is the ONLY place that
mapping lives. In-process models and provider mappers are not v1 surfaces.

See Also:
    contract/CONTRACT.md: The prose encoding spec (source of truth).
    contract/v1/provider-contract.schema.json: Machine-readable field maps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from atomicmemory.memory.types import (
    IngestInput,
    IngestResult,
    Memory,
    Provenance,
    SearchRequest,
    SearchResult,
    SearchResultPage,
)

# No hand-rolled date PARSER: Pydantic v2 accepts trailing-'Z' ISO strings
# natively (regardless of the Python 3.10 stdlib fromisoformat limitation),
# so decode_* just renames keys and lets model validation parse.

# Allowed wire-key sets, one per decoded type, mirroring the `properties` of
# the vendored schemas' $defs (all five declare additionalProperties: false).
# Code literals rather than schema reads because the wheel doesn't ship
# contract/; the conformance harness pins these against the schemas so they
# can't drift. They make the decoders a STRICT v1 boundary: in-process snake
# names (created_at/ranking_score/source_url) and unknown extras are rejected
# instead of slipping through the rename-if-present + extra="ignore" path.
_MEMORY_WIRE_KEYS = frozenset({"id", "content", "scope", "kind", "createdAt", "updatedAt", "provenance", "metadata"})
_PROVENANCE_WIRE_KEYS = frozenset({"source", "sourceUrl", "sourceId", "extractor"})
_SEARCH_RESULT_WIRE_KEYS = frozenset(
    {"memory", "score", "similarity", "rankingScore", "relevance", "version_id", "observed_at"}
)
_SEARCH_RESULT_PAGE_WIRE_KEYS = frozenset({"results", "cursor", "retrieval"})
_INGEST_RESULT_WIRE_KEYS = frozenset({"created", "updated", "unchanged"})


def _require_wire_keys(wire: dict[str, Any], allowed: frozenset[str], type_name: str) -> None:
    """Reject non-v1 wire keys (the schemas declare ``additionalProperties: false``).

    Args:
        wire: The raw wire dict about to be decoded.
        allowed: The type's allowed wire-key set.
        type_name: Human-readable type name for the error message.

    Raises:
        ValueError: If ``wire`` carries any key outside ``allowed`` — covers
            both in-process snake aliases and unknown extras.
    """
    unknown = set(wire) - allowed
    if unknown:
        raise ValueError(
            f"{type_name}: non-v1 wire keys {sorted(unknown)} — the v1 contract uses "
            f"{sorted(allowed)} (in-process snake_case names are not wire names)"
        )


def _to_iso_z(value: datetime) -> str:
    """Emit a datetime as TS ``toISOString()`` equivalent.

    Produces UTC, millisecond precision, trailing Z — matching the
    CONTRACT.md §1 encoding rule. Pydantic's ``model_dump(mode="json")``
    emits seconds-precision (``...12:00:00Z``), NOT the millisecond form
    (``...12:00:00.000Z``), so every datetime field that crosses the v1
    boundary must go through this helper instead of the raw dump.

    Args:
        value: The datetime to encode. If naive, UTC is assumed — bare
            ``astimezone()`` would interpret it as LOCAL system time and
            shift the encoded instant by the host's UTC offset.

    Returns:
        An ISO-8601 string like ``"2026-05-30T12:00:00.123Z"``.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def decode_provenance(wire: dict[str, Any]) -> Provenance:
    """Decode a v1 wire Provenance dict into the in-process model.

    Renames camel fields ``sourceUrl``/``sourceId`` to snake equivalents;
    ``source`` and ``extractor`` are passthrough.

    Args:
        wire: A raw wire-format provenance dict.

    Returns:
        The validated in-process Provenance model.

    Raises:
        ValueError: If ``wire`` carries non-v1 keys.
    """
    _require_wire_keys(wire, _PROVENANCE_WIRE_KEYS, "Provenance")
    data = dict(wire)
    if "sourceUrl" in data:
        data["source_url"] = data.pop("sourceUrl")
    if "sourceId" in data:
        data["source_id"] = data.pop("sourceId")
    return Provenance.model_validate(data)


def encode_provenance(provenance: Provenance) -> dict[str, Any]:
    """Encode the in-process Provenance model into the v1 wire form.

    Renames snake fields ``source_url``/``source_id`` to camel equivalents.
    The schema has ``additionalProperties: false``, so emitting snake names
    would be wire-invalid.

    Args:
        provenance: The in-process provenance model.

    Returns:
        A wire-format dict with ``sourceUrl``/``sourceId`` camel keys.
    """
    data = provenance.model_dump(mode="json", exclude_none=True)
    if "source_url" in data:
        data["sourceUrl"] = data.pop("source_url")
    if "source_id" in data:
        data["sourceId"] = data.pop("source_id")
    return data


def decode_memory(wire: dict[str, Any]) -> Memory:
    """Decode a v1 wire Memory dict (camel dates) into the in-process model.

    Renames ``createdAt``/``updatedAt`` to snake equivalents; routes the
    ``provenance`` sub-object through :func:`decode_provenance`.

    Args:
        wire: A raw wire-format memory dict with camel-cased date fields.

    Returns:
        The validated in-process Memory model.

    Raises:
        ValueError: If ``wire`` carries non-v1 keys.
        pydantic.ValidationError: If ``createdAt`` is missing or any field
            fails validation.
    """
    _require_wire_keys(wire, _MEMORY_WIRE_KEYS, "Memory")
    data = dict(wire)
    if "createdAt" in data:
        data["created_at"] = data.pop("createdAt")
    if "updatedAt" in data:
        data["updated_at"] = data.pop("updatedAt")
    if "provenance" in data and isinstance(data["provenance"], dict):
        data["provenance"] = decode_provenance(data["provenance"]).model_dump(exclude_none=True)
    return Memory.model_validate(data)


def encode_memory(memory: Memory) -> dict[str, Any]:
    """Encode the in-process Memory model into the exact v1 wire form.

    Renames ``created_at``/``updated_at`` to camel equivalents (using
    ``_to_iso_z`` for millisecond precision) and routes ``provenance``
    through :func:`encode_provenance`.

    Args:
        memory: The in-process memory model.

    Returns:
        A wire-format dict with ``createdAt``/``updatedAt`` camel keys.
    """
    data = memory.model_dump(mode="json", exclude_none=True)
    # Replace seconds-precision Pydantic dump with the toISOString millis form.
    data.pop("created_at", None)
    data.pop("updated_at", None)
    data["createdAt"] = _to_iso_z(memory.created_at)
    if memory.updated_at is not None:
        data["updatedAt"] = _to_iso_z(memory.updated_at)
    if memory.provenance is not None:
        data["provenance"] = encode_provenance(memory.provenance)
    if data.get("metadata") is not None:
        # _jsonify must walk the PYTHON-side metadata: the json-mode dump above
        # already stringified any datetime values in the wrong (non-millis) form.
        data["metadata"] = _jsonify(memory.metadata)
    return data


def decode_search_result(wire: dict[str, Any]) -> SearchResult:
    """Decode a v1 wire SearchResult dict into the in-process model.

    Renames ``rankingScore`` to ``ranking_score``; delegates ``memory``
    to :func:`decode_memory`.

    Args:
        wire: A raw wire-format search result dict.

    Returns:
        The validated in-process SearchResult model.

    Raises:
        ValueError: If ``wire`` carries non-v1 keys.
    """
    _require_wire_keys(wire, _SEARCH_RESULT_WIRE_KEYS, "SearchResult")
    data = dict(wire)
    if "rankingScore" in data:
        data["ranking_score"] = data.pop("rankingScore")
    if "memory" in data and isinstance(data["memory"], dict):
        data["memory"] = decode_memory(data["memory"]).model_dump(exclude_none=True)
    return SearchResult.model_validate(data)


def encode_search_result(result: SearchResult) -> dict[str, Any]:
    """Encode the in-process SearchResult model into the v1 wire form.

    Renames ``ranking_score`` to ``rankingScore``; delegates ``memory``
    to :func:`encode_memory`.

    Args:
        result: The in-process search result model.

    Returns:
        A wire-format dict with ``rankingScore`` camel key.
    """
    # exclude_none drops version_id/observed_at when None — deliberately:
    # the TS source (types.ts @ 2a67871) declares both OPTIONAL
    # (`versionId?: string | null`, `observedAt?: string`), so the absent key
    # is the canonical wire form of the None state; a decoded explicit null
    # normalizes to absent on re-encode.
    data = result.model_dump(mode="json", exclude_none=True)
    if "ranking_score" in data:
        data["rankingScore"] = data.pop("ranking_score")
    data["memory"] = encode_memory(result.memory)
    return data


def decode_search_result_page(wire: dict[str, Any]) -> SearchResultPage:
    """Decode a v1 wire SearchResultPage into the in-process model.

    Maps ``results`` through :func:`decode_search_result`; ``cursor`` and
    ``retrieval`` are passthrough (fully snake_case on the wire).

    Args:
        wire: A raw wire-format search result page dict.

    Returns:
        The validated in-process SearchResultPage model.

    Raises:
        ValueError: If ``wire`` carries non-v1 keys.
    """
    _require_wire_keys(wire, _SEARCH_RESULT_PAGE_WIRE_KEYS, "SearchResultPage")
    data = dict(wire)
    data["results"] = [decode_search_result(r).model_dump(exclude_none=True) for r in data.get("results", [])]
    return SearchResultPage.model_validate(data)


def encode_search_result_page(page: SearchResultPage) -> dict[str, Any]:
    """Encode the in-process SearchResultPage model into the v1 wire form.

    Maps ``results`` through :func:`encode_search_result`; ``cursor`` and
    ``retrieval`` are passthrough (fully snake_case on the wire).

    Args:
        page: The in-process search result page model.

    Returns:
        A wire-format dict with each result's ``rankingScore`` camel key.
    """
    data: dict[str, Any] = {
        "results": [encode_search_result(r) for r in page.results],
    }
    if page.cursor is not None:
        data["cursor"] = page.cursor
    if page.retrieval is not None:
        data["retrieval"] = page.retrieval.model_dump(mode="json", exclude_none=True)
    return data


def _jsonify(value: Any) -> Any:
    """Recursively convert datetimes to ``_to_iso_z`` strings.

    Walks dicts and lists, converting any :class:`datetime` encountered to
    the v1 wire form. All other JSON-native values are returned unchanged.
    This covers ``FieldFilter.value`` datetime operands at any nesting depth
    in an ``and``/``or``/``not`` filter tree.

    Args:
        value: A value that may be a dict, list, datetime, or JSON primitive.

    Returns:
        The value with all datetimes replaced by ISO-8601 Z strings.
    """
    if isinstance(value, datetime):
        return _to_iso_z(value)
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    return value


def encode_search_request(request: SearchRequest) -> dict[str, Any]:
    """Encode the in-process SearchRequest into the v1 wire form.

    ``by_alias=True`` is load-bearing: the filter combinator models use
    Python-keyword-safe field names with wire aliases (``and_`` → ``and``,
    ``or_`` → ``or``, ``not_`` → ``not``); a non-alias dump emits the Python
    names which the schema rejects. A recursive ``_jsonify`` walk converts
    any ``datetime`` operands in the filter tree to the toISOString millis
    form (CONTRACT.md §1).

    Args:
        request: The in-process search request model.

    Returns:
        A wire-format dict suitable for JSON serialization.
    """
    raw = request.model_dump(mode="python", by_alias=True, exclude_none=True)
    # _jsonify is typed Any -> Any (it walks arbitrary JSON shapes), but a dict
    # input always yields a dict; a cast keeps the guarantee without a
    # strippable runtime assert (python -O removes asserts).
    return cast("dict[str, Any]", _jsonify(raw))


def decode_search_request(wire: dict[str, Any]) -> SearchRequest:
    """Decode a v1 wire SearchRequest dict into the in-process model.

    SearchRequest fields are fully snake_case on the wire; this is a thin
    ``model_validate`` passthrough.

    Args:
        wire: A raw wire-format search request dict.

    Returns:
        The validated in-process SearchRequest model.
    """
    return SearchRequest.model_validate(wire)


def encode_ingest_input(model: IngestInput) -> dict[str, Any]:
    """Encode the in-process IngestInput model into the v1 wire form.

    Routes ``provenance`` through :func:`encode_provenance`. Raises
    ``ValueError`` if ``content_class`` is set: the v1 schemas have
    ``additionalProperties: false`` with no ``content_class`` field, so
    emitting it would be wire-invalid. This field is Python-ahead; the TS
    contract catch-up is the recorded follow-up.

    Args:
        model: The in-process ingest input model (any mode variant).

    Returns:
        A wire-format dict suitable for JSON serialization.

    Raises:
        ValueError: If the model carries ``content_class`` (Python-only field
            not present in the v1 wire schema).
    """
    # Deliberately generic (getattr, not an isinstance check on a single mode):
    # content_class lives on IngestBase, so every ingest mode carries it and
    # every mode must fail closed here until the v1 contract adds the field.
    content_class = getattr(model, "content_class", None)
    if content_class is not None:
        raise ValueError(
            f"content_class={content_class!r} is a Python-ahead field with no place in the v1 wire "
            "schema (additionalProperties: false). Strip it before encoding, or wait for the TS "
            "contract to add it."
        )
    data = model.model_dump(mode="json", exclude_none=True)
    if "provenance" in data and isinstance(data["provenance"], dict):
        data["provenance"] = encode_provenance(model.provenance)  # type: ignore[arg-type]
    if data.get("metadata") is not None:
        # _jsonify must walk the PYTHON-side metadata: the json-mode dump above
        # already stringified any datetime values in the wrong (non-millis) form.
        data["metadata"] = _jsonify(model.metadata)
    return data


def decode_ingest_result(wire: dict[str, Any]) -> IngestResult:
    """Decode a v1 wire IngestResult dict into the in-process model.

    IngestResult is fully snake_case on the wire; this is a thin
    ``model_validate`` passthrough.

    Args:
        wire: A raw wire-format ingest result dict.

    Returns:
        The validated in-process IngestResult model.

    Raises:
        ValueError: If ``wire`` carries non-v1 keys.
    """
    _require_wire_keys(wire, _INGEST_RESULT_WIRE_KEYS, "IngestResult")
    return IngestResult.model_validate(wire)
