"""AtomicMemoryAgents — agent trust + conflicts category.

Port of the agents section of
`atomicmemory-sdk/src/memory/atomicmemory-provider/handle-impl.ts:1110-1228`.

These routes live under ``/agents/*`` (NOT ``/memories/*``).
``set_trust`` / ``get_trust`` / ``conflicts`` / ``auto_resolve_conflicts``
are user-scoped; ``resolve_conflict`` is keyed by conflict id directly
(core resolves without a user context).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from atomicmemory.providers.atomicmemory.handle import (
    AutoResolveConflictsResult,
    ConflictResolution,
    ConflictsListResult,
    GetTrustResult,
    ResolveConflictResult,
    SetTrustResult,
)
from atomicmemory.providers.atomicmemory.http import HttpOptions, afetch_json, fetch_json

Route = Callable[[str], str]


class AtomicMemoryAgents:
    """Agent trust + conflict resolution operations."""

    def __init__(self, client: httpx.Client, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    def set_trust(
        self,
        user_id: str,
        agent_id: str,
        trust_level: float,
        display_name: str | None = None,
    ) -> SetTrustResult:
        body: dict[str, Any] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "trust_level": trust_level,
        }
        if display_name is not None:
            body["display_name"] = display_name
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/agents/trust"),
            method="PUT",
            json=body,
        )
        return SetTrustResult.model_validate(raw)

    def get_trust(self, user_id: str, agent_id: str) -> GetTrustResult:
        path = self._route(f"/agents/trust?user_id={quote(user_id, safe='')}&agent_id={quote(agent_id, safe='')}")
        raw = fetch_json(self._client, self._http, path)
        return GetTrustResult.model_validate(raw)

    def conflicts(self, user_id: str) -> ConflictsListResult:
        path = self._route(f"/agents/conflicts?user_id={quote(user_id, safe='')}")
        raw = fetch_json(self._client, self._http, path)
        return ConflictsListResult.model_validate(raw)

    def resolve_conflict(self, conflict_id: str, resolution: ConflictResolution) -> ResolveConflictResult:
        path = self._route(f"/agents/conflicts/{quote(conflict_id, safe='')}/resolve")
        raw = fetch_json(
            self._client,
            self._http,
            path,
            method="PUT",
            json={"resolution": resolution},
        )
        return ResolveConflictResult.model_validate(raw)

    def auto_resolve_conflicts(self, user_id: str) -> AutoResolveConflictsResult:
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/agents/conflicts/auto-resolve"),
            method="POST",
            json={"user_id": user_id},
        )
        return AutoResolveConflictsResult.model_validate(raw)


class AsyncAtomicMemoryAgents:
    """Async counterpart of :class:`AtomicMemoryAgents`."""

    def __init__(self, client: httpx.AsyncClient, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    async def set_trust(
        self,
        user_id: str,
        agent_id: str,
        trust_level: float,
        display_name: str | None = None,
    ) -> SetTrustResult:
        body: dict[str, Any] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "trust_level": trust_level,
        }
        if display_name is not None:
            body["display_name"] = display_name
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/agents/trust"),
            method="PUT",
            json=body,
        )
        return SetTrustResult.model_validate(raw)

    async def get_trust(self, user_id: str, agent_id: str) -> GetTrustResult:
        path = self._route(f"/agents/trust?user_id={quote(user_id, safe='')}&agent_id={quote(agent_id, safe='')}")
        raw = await afetch_json(self._client, self._http, path)
        return GetTrustResult.model_validate(raw)

    async def conflicts(self, user_id: str) -> ConflictsListResult:
        path = self._route(f"/agents/conflicts?user_id={quote(user_id, safe='')}")
        raw = await afetch_json(self._client, self._http, path)
        return ConflictsListResult.model_validate(raw)

    async def resolve_conflict(self, conflict_id: str, resolution: ConflictResolution) -> ResolveConflictResult:
        path = self._route(f"/agents/conflicts/{quote(conflict_id, safe='')}/resolve")
        raw = await afetch_json(
            self._client,
            self._http,
            path,
            method="PUT",
            json={"resolution": resolution},
        )
        return ResolveConflictResult.model_validate(raw)

    async def auto_resolve_conflicts(self, user_id: str) -> AutoResolveConflictsResult:
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/agents/conflicts/auto-resolve"),
            method="POST",
            json={"user_id": user_id},
        )
        return AutoResolveConflictsResult.model_validate(raw)
