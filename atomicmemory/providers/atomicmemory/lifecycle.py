"""AtomicMemoryLifecycle — admin lifecycle category.

Port of the lifecycle section of
`atomicmemory-sdk/src/memory/atomicmemory-provider/handle-impl.ts:474-564`.
All routes are user-scoped per core (no workspace_id / agent_id
accepted); cross-workspace admin lives elsewhere.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from atomicmemory.providers.atomicmemory.handle import (
    CapCheckResult,
    ConsolidationExecutionResult,
    ConsolidationResult,
    ConsolidationScanResult,
    DecayResult,
    ReconcileStatus,
    ReconciliationResult,
    ResetSourceResult,
    StatsResult,
)
from atomicmemory.providers.atomicmemory.http import HttpOptions, afetch_json, fetch_json

Route = Callable[[str], str]


def _to_consolidation_result(raw: dict[str, Any]) -> ConsolidationResult:
    if "consolidated_memory_ids" in raw:
        return ConsolidationExecutionResult.model_validate(raw)
    return ConsolidationScanResult.model_validate(raw)


class AtomicMemoryLifecycle:
    """Lifecycle admin operations for a user."""

    def __init__(self, client: httpx.Client, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    def consolidate(self, user_id: str, execute: bool = False) -> ConsolidationResult:
        body: dict[str, Any] = {"user_id": user_id}
        if execute:
            body["execute"] = True
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/consolidate"),
            method="POST",
            json=body,
        )
        return _to_consolidation_result(raw)

    def decay(self, user_id: str, dry_run: bool = True) -> DecayResult:
        body: dict[str, Any] = {"user_id": user_id}
        # Core treats dry_run as true unless explicitly false; only forward
        # the flag when the caller opted into a non-dry pass.
        if dry_run is False:
            body["dry_run"] = False
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/decay"),
            method="POST",
            json=body,
        )
        return DecayResult.model_validate(raw)

    def cap(self, user_id: str) -> CapCheckResult:
        path = self._route(f"/memories/cap?user_id={user_id}")
        raw = fetch_json(self._client, self._http, path)
        return CapCheckResult.model_validate(raw)

    def stats(self, user_id: str) -> StatsResult:
        path = self._route(f"/memories/stats?user_id={user_id}")
        raw = fetch_json(self._client, self._http, path)
        return StatsResult.model_validate(raw)

    def reset_source(self, user_id: str, source_site: str) -> ResetSourceResult:
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/reset-source"),
            method="POST",
            json={"user_id": user_id, "source_site": source_site},
        )
        return ResetSourceResult.model_validate(raw)

    def reconcile(self, user_id: str) -> ReconciliationResult:
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/reconcile"),
            method="POST",
            json={"user_id": user_id},
        )
        return ReconciliationResult.model_validate(raw)

    def reconcile_all(self) -> ReconciliationResult:
        """Run reconciliation across every user (privileged batch pass).

        Maps to the no-``user_id`` branch of core's ``POST
        /memories/reconcile`` route.
        """
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/reconcile"),
            method="POST",
            json={},
        )
        return ReconciliationResult.model_validate(raw)

    def reconcile_status(self, user_id: str) -> ReconcileStatus:
        path = self._route(f"/memories/reconcile/status?user_id={user_id}")
        raw = fetch_json(self._client, self._http, path)
        return ReconcileStatus.model_validate(raw)


class AsyncAtomicMemoryLifecycle:
    """Async counterpart of :class:`AtomicMemoryLifecycle`."""

    def __init__(self, client: httpx.AsyncClient, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    async def consolidate(self, user_id: str, execute: bool = False) -> ConsolidationResult:
        body: dict[str, Any] = {"user_id": user_id}
        if execute:
            body["execute"] = True
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/consolidate"),
            method="POST",
            json=body,
        )
        return _to_consolidation_result(raw)

    async def decay(self, user_id: str, dry_run: bool = True) -> DecayResult:
        body: dict[str, Any] = {"user_id": user_id}
        if dry_run is False:
            body["dry_run"] = False
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/decay"),
            method="POST",
            json=body,
        )
        return DecayResult.model_validate(raw)

    async def cap(self, user_id: str) -> CapCheckResult:
        path = self._route(f"/memories/cap?user_id={user_id}")
        raw = await afetch_json(self._client, self._http, path)
        return CapCheckResult.model_validate(raw)

    async def stats(self, user_id: str) -> StatsResult:
        path = self._route(f"/memories/stats?user_id={user_id}")
        raw = await afetch_json(self._client, self._http, path)
        return StatsResult.model_validate(raw)

    async def reset_source(self, user_id: str, source_site: str) -> ResetSourceResult:
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/reset-source"),
            method="POST",
            json={"user_id": user_id, "source_site": source_site},
        )
        return ResetSourceResult.model_validate(raw)

    async def reconcile(self, user_id: str) -> ReconciliationResult:
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/reconcile"),
            method="POST",
            json={"user_id": user_id},
        )
        return ReconciliationResult.model_validate(raw)

    async def reconcile_all(self) -> ReconciliationResult:
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/reconcile"),
            method="POST",
            json={},
        )
        return ReconciliationResult.model_validate(raw)

    async def reconcile_status(self, user_id: str) -> ReconcileStatus:
        path = self._route(f"/memories/reconcile/status?user_id={user_id}")
        raw = await afetch_json(self._client, self._http, path)
        return ReconcileStatus.model_validate(raw)
