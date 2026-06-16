"""Synchronous client for the /v1/entities API.

Mirrors the structure of ``atomicmemory/storage/client.py``:
Pydantic config model with camelCase aliases, an httpx.Client, a
``_request`` helper that wraps network/non-2xx failures, and
close/context-manager support.

Two deliberate divergences from the storage client:
- ``EntitiesClientConfig`` has no ``user_id``; the entities API only
  requires ``api_url`` and ``api_key``.
- Headers are ``Authorization: Bearer {api_key}`` only (no
  ``X-AtomicMemory-User-Id``).

Shared decode/validate helpers (``_decode_json``, ``_validate_response``,
``_decode_attributes_envelope``) are imported by the async client to avoid
duplication.  All 2xx decode/validate failures raise
:class:`~atomicmemory.entities.errors.EntitiesClientError` with
``error_code="invalid_entities_response"`` so raw ``JSONDecodeError``,
``ValidationError``, and ``AttributeError`` never escape the public surface.
"""

from __future__ import annotations

import builtins
import json
from types import TracebackType
from typing import Any, TypeVar, cast
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from atomicmemory.core.url import validate_api_url
from atomicmemory.entities.errors import EntitiesClientError
from atomicmemory.entities.types import (
    DeleteEntityResult,
    EntityAttribute,
    EntityDetail,
    EntityListResult,
    EntityProfile,
    EntitySettings,
    EntityType,
    MemoryHistory,
    MergeEntitiesResult,
)

# TypeVar used by the shared response-validation helpers below.
_ModelT = TypeVar("_ModelT")

# Maximum body text length included in invalid-response error messages.
_BODY_PREVIEW_LEN = 200

# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


class EntitiesClientConfig(BaseModel):
    """Configuration for the sync and async entities clients."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_url: str = Field(alias="apiUrl")
    api_key: SecretStr = Field(alias="apiKey")
    timeout_seconds: float = Field(default=30.0, alias="timeoutSeconds")
    allow_private_networks: bool = Field(default=True, alias="allowPrivateNetworks")
    """Permit loopback/private/reserved IP literals in ``api_url`` (default True;
    set False to harden). Link-local / cloud-metadata stay blocked regardless."""

    @model_validator(mode="after")
    def _validate_api_url(self) -> EntitiesClientConfig:
        self.api_url = validate_api_url(self.api_url, allow_private_networks=self.allow_private_networks)
        return self

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: object) -> object:
        # Validate before SecretStr wraps the value so we can call .strip().
        if isinstance(value, str) and value.strip() == "":
            raise ValueError("api_key must not be empty")
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------


class EntitiesClient:
    """Sync entry point for the /v1/entities API."""

    def __init__(self, config: EntitiesClientConfig | dict[str, Any]) -> None:
        """Create an EntitiesClient.

        Args:
            config: An ``EntitiesClientConfig`` instance or a plain dict
                    with ``apiUrl``/``apiKey`` (and optionally
                    ``timeoutSeconds``) keys.
        """
        self._config = _coerce_config(config)
        self._api_url = self._config.api_url.rstrip("/")
        self._client = httpx.Client(timeout=self._config.timeout_seconds)

    def profile(self, entity_id: str, *, entity_type: EntityType = "user") -> EntityProfile:
        """Get the synthesized profile for an entity.

        Args:
            entity_id: The entity identifier (URL-encoded automatically).
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            The entity's ``EntityProfile``.
        """
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}/profile"
        response = self._request("GET", path)
        return _validate_response(EntityProfile, _decode_json("GET", path, response), "EntityProfile", "GET", path)

    def list(
        self,
        *,
        entity_type: EntityType | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> EntityListResult:
        """List all entities with memory counts (paginated).

        Args:
            entity_type: Filter by entity namespace.
            page: 1-based page number.
            page_size: Page size.

        Returns:
            ``EntityListResult`` with entities and pagination metadata.
        """
        params = _build_params(entity_type=entity_type, page=page, page_size=page_size)
        path = "/v1/entities" + (_qs(params) if params else "")
        response = self._request("GET", path)
        data = _decode_json("GET", path, response)
        return _validate_response(EntityListResult, data, "EntityListResult", "GET", path)

    def get(self, entity_id: str, *, entity_type: EntityType = "user") -> EntityDetail:
        """Get entity detail — attributes, relations, and recent cards.

        Args:
            entity_id: The entity identifier.
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            ``EntityDetail`` with full attribute/relation/card data.
        """
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}"
        response = self._request("GET", path)
        return _validate_response(EntityDetail, _decode_json("GET", path, response), "EntityDetail", "GET", path)

    def delete(self, entity_id: str, *, entity_type: EntityType = "user") -> DeleteEntityResult:
        """Cascade-delete all data for an entity.

        Args:
            entity_id: The entity identifier.
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            ``DeleteEntityResult`` with six row-count fields.
        """
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}"
        response = self._request("DELETE", path)
        data = _decode_json("DELETE", path, response)
        return _validate_response(DeleteEntityResult, data, "DeleteEntityResult", "DELETE", path)

    def attributes(
        self,
        entity_id: str,
        *,
        entity_type: EntityType = "user",
        attribute: str | None = None,
        entity: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[EntityAttribute]:
        """Get structured attribute triples for an entity.

        Unwraps the ``{"attributes": [...]}`` envelope; absent key → ``[]``.

        Args:
            entity_id: The entity identifier.
            entity_type: Entity namespace; defaults to ``"user"``.
            attribute: Filter by attribute name.
            entity: Filter by related entity.
            limit: Maximum number of results.

        Returns:
            List of ``EntityAttribute`` instances.
        """
        params = _build_params(attribute=attribute, entity=entity, limit=limit)
        qs = _qs(params) if params else ""
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}/attributes{qs}"
        body = _decode_json("GET", path, self._request("GET", path))
        return _decode_attributes_envelope(body, "GET", path)

    def memory_history(self, entity_id: str, memory_id: str, *, entity_type: EntityType = "user") -> MemoryHistory:
        """Get the mutation history of a single memory record.

        Args:
            entity_id: The entity identifier.
            memory_id: The memory identifier (URL-encoded automatically).
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            ``MemoryHistory`` with versioned history entries.
        """
        etype = _validate_entity_type(entity_type)
        path = f"/v1/entities/{etype}/{_quote(entity_id)}/memories/{_quote(memory_id)}/history"
        response = self._request("GET", path)
        return _validate_response(MemoryHistory, _decode_json("GET", path, response), "MemoryHistory", "GET", path)

    def patch_settings(
        self,
        entity_id: str,
        *,
        entity_type: EntityType = "user",
        extraction_prompt: str | None = None,
        memory_kinds: builtins.list[str] | None = None,
        decay_enabled: bool | None = None,
    ) -> EntitySettings:
        """Update per-entity extraction guidance and pipeline config.

        Only the kwargs explicitly provided are included in the request body.

        Args:
            entity_id: The entity identifier.
            entity_type: Entity namespace; defaults to ``"user"``.
            extraction_prompt: Custom extraction prompt for this entity.
            memory_kinds: Allowed memory kind filters.
            decay_enabled: Whether memory decay is active.

        Returns:
            Updated ``EntitySettings``.
        """
        body = _settings_body(extraction_prompt, memory_kinds, decay_enabled)
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}/settings"
        response = self._request(
            "PATCH",
            path,
            headers={"Content-Type": "application/json"},
            content=json.dumps(body, separators=(",", ":")).encode(),
        )
        data = _decode_json("PATCH", path, response)
        return _validate_response(EntitySettings, data, "EntitySettings", "PATCH", path)

    def merge(
        self,
        source_entity_id: str,
        target_entity_id: str,
        *,
        source_entity_type: EntityType = "user",
        target_entity_type: EntityType = "user",
    ) -> MergeEntitiesResult:
        """Merge a source entity into a target entity.

        Args:
            source_entity_id: The entity to merge from.
            target_entity_id: The entity to merge into.
            source_entity_type: Source entity namespace; defaults to ``"user"``.
            target_entity_type: Target entity namespace; defaults to ``"user"``.

        Returns:
            ``MergeEntitiesResult`` with moved-row counts.
        """
        body = {
            "source": {"entity_type": _validate_entity_type(source_entity_type), "entity_id": source_entity_id},
            "target": {"entity_type": _validate_entity_type(target_entity_type), "entity_id": target_entity_id},
        }
        merge_path = "/v1/entities/merge"
        response = self._request(
            "POST",
            merge_path,
            headers={"Content-Type": "application/json"},
            content=json.dumps(body, separators=(",", ":")).encode(),
        )
        data = _decode_json("POST", merge_path, response)
        return _validate_response(MergeEntitiesResult, data, "MergeEntitiesResult", "POST", merge_path)

    def close(self) -> None:
        """Close the underlying httpx.Client and release connections."""
        self._client.close()

    def __enter__(self) -> EntitiesClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                f"{self._api_url}{path}",
                headers=_auth_headers(self._config.api_key, headers),
                content=content,
            )
        except httpx.RequestError as exc:
            raise _network_error(method, path, exc) from exc
        if response.is_success:
            return response
        raise _http_error(method, path, response)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _coerce_config(value: EntitiesClientConfig | dict[str, Any]) -> EntitiesClientConfig:
    if isinstance(value, EntitiesClientConfig):
        return value
    try:
        return EntitiesClientConfig.model_validate(value)
    except PydanticValidationError as exc:
        raise EntitiesClientError(
            f"Invalid EntitiesClientConfig: {exc}",
            error_code="invalid_entities_input",
            status=0,
            body_text="",
        ) from exc


def _validate_entity_type(value: str) -> str:
    """Guard entity_type path segments against non-allowlist values.

    Raises ``EntitiesClientError`` with ``error_code="invalid_entities_input"``
    when *value* is not one of the three recognised entity types.  Callers
    embed the return value directly into URL paths so the check fires before
    any HTTP call.

    Args:
        value: The raw entity_type string supplied by the caller.

    Returns:
        The validated entity_type string (unchanged).
    """
    _VALID = {"user", "agent", "session"}
    if value not in _VALID:
        raise EntitiesClientError(
            f"invalid entity_type {value!r}: must be one of user/agent/session",
            error_code="invalid_entities_input",
            status=0,
            body_text="",
        )
    return value


def _quote(value: str) -> str:
    return quote(value, safe="")


def _auth_headers(api_key: SecretStr, extra: dict[str, str] | None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key.get_secret_value()}"}
    if extra:
        headers.update(extra)
    return headers


def _build_params(**kwargs: Any) -> dict[str, str]:
    """Return a dict of query params for only the non-None kwargs."""
    return {k: str(v) for k, v in kwargs.items() if v is not None}


def _settings_body(
    extraction_prompt: str | None,
    memory_kinds: builtins.list[str] | None,
    decay_enabled: bool | None,
) -> dict[str, Any]:
    """Return a settings PATCH body containing only the provided fields."""
    body: dict[str, Any] = {}
    if extraction_prompt is not None:
        body["extraction_prompt"] = extraction_prompt
    if memory_kinds is not None:
        body["memory_kinds"] = memory_kinds
    if decay_enabled is not None:
        body["decay_enabled"] = decay_enabled
    return body


def _qs(params: dict[str, str]) -> str:
    return f"?{urlencode(params)}"


def _http_error(method: str, path: str, response: httpx.Response) -> EntitiesClientError:
    return EntitiesClientError(
        f"EntitiesClient: {method} {path} failed with {response.status_code}: {response.text}",
        error_code="entities_request_failed",
        status=response.status_code,
        body_text=response.text,
    )


def _network_error(method: str, path: str, exc: httpx.RequestError) -> EntitiesClientError:
    return EntitiesClientError(
        f"Network error while calling {method} {path}: {exc}",
        error_code="network_error",
        status=0,
        body_text="",
    )


def _decode_json(method: str, path: str, response: httpx.Response) -> Any:
    """Decode the response body as JSON; raise EntitiesClientError on failure.

    Wraps ``response.json()`` so that ``ValueError``/``JSONDecodeError`` never
    escapes the public surface.

    Args:
        method: HTTP method (for the error message).
        path: Request path (for the error message).
        response: The 2xx httpx.Response to decode.

    Returns:
        The parsed JSON value (any JSON type).
    """
    try:
        return response.json()
    except ValueError as exc:
        preview = response.text[:_BODY_PREVIEW_LEN]
        raise EntitiesClientError(
            f"EntitiesClient: {method} {path} — server returned invalid JSON: {exc}",
            error_code="invalid_entities_response",
            status=response.status_code,
            body_text=preview,
        ) from exc


def _validate_response(model: type[_ModelT], data: Any, type_name: str, method: str, path: str) -> _ModelT:
    """Validate a decoded JSON value against a Pydantic model.

    Raises ``EntitiesClientError`` for non-object data or Pydantic validation
    failures — never lets ``ValidationError`` or ``AttributeError`` escape.

    Args:
        model: The Pydantic model class to validate against.
        data: The decoded JSON value (expected to be a dict).
        type_name: Human-readable model name for error messages.
        method: HTTP method (for the error message).
        path: Request path (for the error message).

    Returns:
        A validated instance of ``model``.
    """
    if not isinstance(data, dict):
        raise EntitiesClientError(
            f"{type_name}: server response is not a JSON object",
            error_code="invalid_entities_response",
            status=200,
            body_text="",
        )
    try:
        return cast("_ModelT", model.model_validate(data))  # type: ignore[attr-defined]
    except PydanticValidationError as exc:
        raise EntitiesClientError(
            f"{type_name}: server response failed validation",
            error_code="invalid_entities_response",
            status=200,
            body_text="",
            context={"type": type_name, "errors": exc.errors()},
        ) from exc


def _decode_attributes_envelope(body: Any, method: str, path: str) -> builtins.list[EntityAttribute]:
    """Unwrap and validate the ``{"attributes": [...]}`` envelope.

    Validates that ``body`` is a dict and that the ``attributes`` value, when
    present, is a list.  Each item is validated via ``_validate_response``.

    Args:
        body: The already-decoded JSON value from the response.
        method: HTTP method (for the error message).
        path: Request path (for the error message).

    Returns:
        List of ``EntityAttribute`` instances (empty list if key absent).
    """
    if not isinstance(body, dict):
        raise EntitiesClientError(
            "EntityAttribute: server response is not a JSON object",
            error_code="invalid_entities_response",
            status=200,
            body_text="",
        )
    raw_attrs = body.get("attributes")
    if raw_attrs is None:
        return []
    if not isinstance(raw_attrs, builtins.list):
        raise EntitiesClientError(
            "EntityAttribute: 'attributes' envelope value is not a list",
            error_code="invalid_entities_response",
            status=200,
            body_text="",
        )
    return [_validate_response(EntityAttribute, item, "EntityAttribute", method, path) for item in raw_attrs]
