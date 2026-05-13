"""AtomicMemoryAudit — mutation audit category.

Port of the audit section of
`atomicmemory-sdk/src/memory/atomicmemory-provider/handle-impl.ts:720-880`.
All routes are user-scoped.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

import httpx

from atomicmemory.providers.atomicmemory.handle import (
    AuditTrailResult,
    MutationSummary,
    RecentMutationsResult,
)
from atomicmemory.providers.atomicmemory.http import HttpOptions, afetch_json, fetch_json

Route = Callable[[str], str]


class AtomicMemoryAudit:
    """Audit-trail accessors for a user's claim-version history."""

    def __init__(self, client: httpx.Client, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    def summary(self, user_id: str) -> MutationSummary:
        path = self._route(f"/memories/audit/summary?user_id={quote(user_id, safe='')}")
        raw = fetch_json(self._client, self._http, path)
        return MutationSummary.model_validate(raw)

    def recent(self, user_id: str, limit: int | None = None) -> RecentMutationsResult:
        url = f"/memories/audit/recent?user_id={quote(user_id, safe='')}"
        if limit is not None:
            url += f"&limit={limit}"
        raw = fetch_json(self._client, self._http, self._route(url))
        return RecentMutationsResult.model_validate(raw)

    def trail(self, memory_id: str, user_id: str) -> AuditTrailResult:
        path = self._route(f"/memories/{quote(memory_id, safe='')}/audit?user_id={quote(user_id, safe='')}")
        raw = fetch_json(self._client, self._http, path)
        return AuditTrailResult.model_validate(raw)


class AsyncAtomicMemoryAudit:
    """Async counterpart of :class:`AtomicMemoryAudit`."""

    def __init__(self, client: httpx.AsyncClient, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    async def summary(self, user_id: str) -> MutationSummary:
        path = self._route(f"/memories/audit/summary?user_id={quote(user_id, safe='')}")
        raw = await afetch_json(self._client, self._http, path)
        return MutationSummary.model_validate(raw)

    async def recent(self, user_id: str, limit: int | None = None) -> RecentMutationsResult:
        url = f"/memories/audit/recent?user_id={quote(user_id, safe='')}"
        if limit is not None:
            url += f"&limit={limit}"
        raw = await afetch_json(self._client, self._http, self._route(url))
        return RecentMutationsResult.model_validate(raw)

    async def trail(self, memory_id: str, user_id: str) -> AuditTrailResult:
        path = self._route(f"/memories/{quote(memory_id, safe='')}/audit?user_id={quote(user_id, safe='')}")
        raw = await afetch_json(self._client, self._http, path)
        return AuditTrailResult.model_validate(raw)
