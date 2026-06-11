"""Async client for the /v1/entities API.

The async surface mirrors :mod:`atomicmemory.entities.client` while using
``httpx.AsyncClient`` for every request.  All private helpers (query/body
builders, path encoding, error construction, config coercion) are imported
from the sync module — no duplication.
"""

from __future__ import annotations

import builtins
import json
from types import TracebackType
from typing import Any

import httpx

from atomicmemory.entities.client import (
    EntitiesClientConfig,
    _auth_headers,
    _build_params,
    _coerce_config,
    _decode_attributes_envelope,
    _decode_json,
    _http_error,
    _network_error,
    _qs,
    _quote,
    _settings_body,
    _validate_entity_type,
    _validate_response,
)
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


class AsyncEntitiesClient:
    """Async entry point for the /v1/entities API."""

    def __init__(self, config: EntitiesClientConfig | dict[str, Any]) -> None:
        """Create an AsyncEntitiesClient.

        Args:
            config: An ``EntitiesClientConfig`` instance or a plain dict
                    with ``apiUrl``/``apiKey`` (and optionally
                    ``timeoutSeconds``) keys.
        """
        self._config = _coerce_config(config)
        self._api_url = self._config.api_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=self._config.timeout_seconds)

    async def profile(self, entity_id: str, *, entity_type: EntityType = "user") -> EntityProfile:
        """Get the synthesized profile for an entity.

        # Mirrors EntitiesClient.profile — keep in sync.

        Args:
            entity_id: The entity identifier (URL-encoded automatically).
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            The entity's ``EntityProfile``.
        """
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}/profile"
        response = await self._request("GET", path)
        return _validate_response(EntityProfile, _decode_json("GET", path, response), "EntityProfile", "GET", path)

    async def list(
        self,
        *,
        entity_type: EntityType | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> EntityListResult:
        """List all entities with memory counts (paginated).

        # Mirrors EntitiesClient.list — keep in sync.

        Args:
            entity_type: Filter by entity namespace.
            page: 1-based page number.
            page_size: Page size.

        Returns:
            ``EntityListResult`` with entities and pagination metadata.
        """
        params = _build_params(entity_type=entity_type, page=page, page_size=page_size)
        path = "/v1/entities" + (_qs(params) if params else "")
        response = await self._request("GET", path)
        data = _decode_json("GET", path, response)
        return _validate_response(EntityListResult, data, "EntityListResult", "GET", path)

    async def get(self, entity_id: str, *, entity_type: EntityType = "user") -> EntityDetail:
        """Get entity detail — attributes, relations, and recent cards.

        # Mirrors EntitiesClient.get — keep in sync.

        Args:
            entity_id: The entity identifier.
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            ``EntityDetail`` with full attribute/relation/card data.
        """
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}"
        response = await self._request("GET", path)
        return _validate_response(EntityDetail, _decode_json("GET", path, response), "EntityDetail", "GET", path)

    async def delete(self, entity_id: str, *, entity_type: EntityType = "user") -> DeleteEntityResult:
        """Cascade-delete all data for an entity.

        # Mirrors EntitiesClient.delete — keep in sync.

        Args:
            entity_id: The entity identifier.
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            ``DeleteEntityResult`` with six row-count fields.
        """
        path = f"/v1/entities/{_validate_entity_type(entity_type)}/{_quote(entity_id)}"
        response = await self._request("DELETE", path)
        data = _decode_json("DELETE", path, response)
        return _validate_response(DeleteEntityResult, data, "DeleteEntityResult", "DELETE", path)

    async def attributes(
        self,
        entity_id: str,
        *,
        entity_type: EntityType = "user",
        attribute: str | None = None,
        entity: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[EntityAttribute]:
        """Get structured attribute triples for an entity.

        # Mirrors EntitiesClient.attributes — keep in sync.

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
        body = _decode_json("GET", path, await self._request("GET", path))
        return _decode_attributes_envelope(body, "GET", path)

    async def memory_history(
        self, entity_id: str, memory_id: str, *, entity_type: EntityType = "user"
    ) -> MemoryHistory:
        """Get the mutation history of a single memory record.

        # Mirrors EntitiesClient.memory_history — keep in sync.

        Args:
            entity_id: The entity identifier.
            memory_id: The memory identifier (URL-encoded automatically).
            entity_type: Entity namespace; defaults to ``"user"``.

        Returns:
            ``MemoryHistory`` with versioned history entries.
        """
        etype = _validate_entity_type(entity_type)
        path = f"/v1/entities/{etype}/{_quote(entity_id)}/memories/{_quote(memory_id)}/history"
        response = await self._request("GET", path)
        return _validate_response(MemoryHistory, _decode_json("GET", path, response), "MemoryHistory", "GET", path)

    async def patch_settings(
        self,
        entity_id: str,
        *,
        entity_type: EntityType = "user",
        extraction_prompt: str | None = None,
        memory_kinds: builtins.list[str] | None = None,
        decay_enabled: bool | None = None,
    ) -> EntitySettings:
        """Update per-entity extraction guidance and pipeline config.

        # Mirrors EntitiesClient.patch_settings — keep in sync.

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
        response = await self._request(
            "PATCH",
            path,
            headers={"Content-Type": "application/json"},
            content=json.dumps(body, separators=(",", ":")).encode(),
        )
        data = _decode_json("PATCH", path, response)
        return _validate_response(EntitySettings, data, "EntitySettings", "PATCH", path)

    async def merge(
        self,
        source_entity_id: str,
        target_entity_id: str,
        *,
        source_entity_type: EntityType = "user",
        target_entity_type: EntityType = "user",
    ) -> MergeEntitiesResult:
        """Merge a source entity into a target entity.

        # Mirrors EntitiesClient.merge — keep in sync.

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
        response = await self._request(
            "POST",
            merge_path,
            headers={"Content-Type": "application/json"},
            content=json.dumps(body, separators=(",", ":")).encode(),
        )
        data = _decode_json("POST", merge_path, response)
        return _validate_response(MergeEntitiesResult, data, "MergeEntitiesResult", "POST", merge_path)

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient and release connections."""
        await self._client.aclose()

    async def __aenter__(self) -> AsyncEntitiesClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(
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
