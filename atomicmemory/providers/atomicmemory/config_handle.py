"""AtomicMemoryConfig — runtime config category.

Port of the config section of
`atomicmemory-sdk/src/memory/atomicmemory-provider/handle-impl.ts:1008-1098`.
``health`` is global; ``update_config`` is gated on
``CORE_RUNTIME_CONFIG_MUTATION_ENABLED`` server-side.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx

from atomicmemory.providers.atomicmemory.handle import (
    AtomicMemoryHealthStatus,
    ConfigUpdateResult,
    ConfigUpdates,
    HealthConfig,
)
from atomicmemory.providers.atomicmemory.http import HttpOptions, afetch_json, fetch_json

Route = Callable[[str], str]

_SNAKE_TO_CAMEL_RE = re.compile(r"_([a-z])")


def _snake_to_camel(value: str) -> str:
    """Convert a snake_case identifier to camelCase.

    Mirrors TS handle-impl.ts: applied field names are echoed back to
    Python in the same camelCase the TS SDK uses. Pure cosmetic; the
    actual config payload is already mapped via Pydantic.
    """
    return _SNAKE_TO_CAMEL_RE.sub(lambda m: m.group(1).upper(), value)


class AtomicMemoryConfig:
    """Runtime configuration accessors."""

    def __init__(self, client: httpx.Client, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    def health(self) -> AtomicMemoryHealthStatus:
        raw = fetch_json(self._client, self._http, self._route("/memories/health"))
        return AtomicMemoryHealthStatus.model_validate(
            {"status": raw.get("status", "ok"), "config": HealthConfig.model_validate(raw["config"])}
        )

    def update_config(self, updates: ConfigUpdates | dict[str, Any]) -> ConfigUpdateResult:
        if isinstance(updates, dict):
            updates = ConfigUpdates.model_validate(updates)
        body: dict[str, Any] = {}
        if updates.similarity_threshold is not None:
            body["similarity_threshold"] = updates.similarity_threshold
        if updates.audn_candidate_threshold is not None:
            body["audn_candidate_threshold"] = updates.audn_candidate_threshold
        if updates.clarification_conflict_threshold is not None:
            body["clarification_conflict_threshold"] = updates.clarification_conflict_threshold
        if updates.max_search_results is not None:
            body["max_search_results"] = updates.max_search_results
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/config"),
            method="PUT",
            json=body,
        )
        applied = [_snake_to_camel(name) for name in raw.get("applied", [])]
        return ConfigUpdateResult.model_validate(
            {
                "applied": applied,
                "config": HealthConfig.model_validate(raw["config"]),
                "note": raw.get("note", ""),
            }
        )


class AsyncAtomicMemoryConfig:
    """Async counterpart of :class:`AtomicMemoryConfig`."""

    def __init__(self, client: httpx.AsyncClient, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    async def health(self) -> AtomicMemoryHealthStatus:
        raw = await afetch_json(self._client, self._http, self._route("/memories/health"))
        return AtomicMemoryHealthStatus.model_validate(
            {"status": raw.get("status", "ok"), "config": HealthConfig.model_validate(raw["config"])}
        )

    async def update_config(self, updates: ConfigUpdates | dict[str, Any]) -> ConfigUpdateResult:
        if isinstance(updates, dict):
            updates = ConfigUpdates.model_validate(updates)
        body: dict[str, Any] = {}
        if updates.similarity_threshold is not None:
            body["similarity_threshold"] = updates.similarity_threshold
        if updates.audn_candidate_threshold is not None:
            body["audn_candidate_threshold"] = updates.audn_candidate_threshold
        if updates.clarification_conflict_threshold is not None:
            body["clarification_conflict_threshold"] = updates.clarification_conflict_threshold
        if updates.max_search_results is not None:
            body["max_search_results"] = updates.max_search_results
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/config"),
            method="PUT",
            json=body,
        )
        applied = [_snake_to_camel(name) for name in raw.get("applied", [])]
        return ConfigUpdateResult.model_validate(
            {
                "applied": applied,
                "config": HealthConfig.model_validate(raw["config"]),
                "note": raw.get("note", ""),
            }
        )
