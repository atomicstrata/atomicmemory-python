"""Async AtomicMemoryHandle root implementation.

Async counterpart of :mod:`atomicmemory.providers.atomicmemory.handle_impl`.
Reuses the same scope mappers, body construction, and response shaping
helpers; the only difference is awaiting the HTTP transport.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from atomicmemory.core.errors import ProviderError
from atomicmemory.providers.atomicmemory.agents import AsyncAtomicMemoryAgents
from atomicmemory.providers.atomicmemory.audit import AsyncAtomicMemoryAudit
from atomicmemory.providers.atomicmemory.config_handle import AsyncAtomicMemoryConfig
from atomicmemory.providers.atomicmemory.handle import (
    AtomicMemoryIngestInput,
    AtomicMemoryIngestResult,
    AtomicMemoryListOptions,
    AtomicMemoryListResultPage,
    AtomicMemoryMemory,
    AtomicMemorySearchRequest,
    AtomicMemorySearchResultPage,
    MemoryScope,
    WorkspaceScope,
)
from atomicmemory.providers.atomicmemory.handle_impl import (
    _assert_list_options_scope_compat,
    _coerce_list_options,
    _map_search_response,
    _to_atomic_memory,
)
from atomicmemory.providers.atomicmemory.http import (
    HttpOptions,
    afetch_json,
    afetch_json_or_none,
    afetch_void,
)
from atomicmemory.providers.atomicmemory.lessons import AsyncAtomicMemoryLessons
from atomicmemory.providers.atomicmemory.lifecycle import AsyncAtomicMemoryLifecycle
from atomicmemory.providers.atomicmemory.scope_mapper import (
    assert_scope_allows_visibility,
    scope_to_fields,
    scope_to_query_pairs,
    strip_agent_scope,
    strip_read_filters,
)

Route = Callable[[str], str]


class AsyncAtomicMemoryHandle:
    """Async typed handle for AtomicMemory-specific routes."""

    def __init__(self, client: httpx.AsyncClient, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route
        self.lifecycle = AsyncAtomicMemoryLifecycle(client, http, route)
        self.audit = AsyncAtomicMemoryAudit(client, http, route)
        self.lessons = AsyncAtomicMemoryLessons(client, http, route)
        self.config = AsyncAtomicMemoryConfig(client, http, route)
        self.agents = AsyncAtomicMemoryAgents(client, http, route)

    async def ingest_full(self, input: AtomicMemoryIngestInput, scope: MemoryScope) -> AtomicMemoryIngestResult:
        return await self._post_ingest(self._route("/memories/ingest"), input, scope)

    async def ingest_quick(
        self,
        input: AtomicMemoryIngestInput,
        scope: MemoryScope,
        skip_extraction: bool = False,
    ) -> AtomicMemoryIngestResult:
        return await self._post_ingest(
            self._route("/memories/ingest/quick"), input, scope, skip_extraction=skip_extraction
        )

    async def search(self, request: AtomicMemorySearchRequest, scope: MemoryScope) -> AtomicMemorySearchResultPage:
        return await self._post_search(self._route("/memories/search"), request, scope)

    async def search_fast(self, request: AtomicMemorySearchRequest, scope: MemoryScope) -> AtomicMemorySearchResultPage:
        return await self._post_search(self._route("/memories/search/fast"), request, scope)

    async def expand(self, refs: list[str], scope: MemoryScope) -> list[AtomicMemoryMemory]:
        body: dict[str, Any] = {**scope_to_fields(scope), "memory_ids": refs}
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/expand"),
            method="POST",
            json=body,
        )
        echoed = strip_read_filters(scope)
        return [_to_atomic_memory(m, echoed) for m in raw.get("memories", [])]

    async def list(
        self,
        scope: MemoryScope,
        options: AtomicMemoryListOptions | dict[str, Any] | None = None,
    ) -> AtomicMemoryListResultPage:
        opts = _coerce_list_options(options)
        _assert_list_options_scope_compat(scope, opts)
        pairs: list[tuple[str, str]] = scope_to_query_pairs(scope, include_thread=True)
        if opts.limit is not None:
            pairs.append(("limit", str(opts.limit)))
        if opts.offset is not None:
            pairs.append(("offset", str(opts.offset)))
        if opts.source_site:
            pairs.append(("source_site", opts.source_site))
        if opts.episode_id:
            pairs.append(("episode_id", opts.episode_id))
        path = self._route(f"/memories/list?{urlencode(pairs)}")
        raw = await afetch_json(self._client, self._http, path)
        limit = opts.limit if opts.limit is not None else 20
        offset = opts.offset if opts.offset is not None else 0
        memories_raw = raw.get("memories", [])
        next_offset = offset + len(memories_raw)
        has_more = len(memories_raw) == limit
        echoed = strip_agent_scope(scope)
        return AtomicMemoryListResultPage(
            memories=[_to_atomic_memory(m, echoed) for m in memories_raw],
            count=raw.get("count", len(memories_raw)),
            cursor=str(next_offset) if has_more else None,
        )

    async def get(self, id: str, scope: MemoryScope) -> AtomicMemoryMemory | None:
        unfiltered_scope = strip_read_filters(scope)
        path = self._route(f"/memories/{quote(id, safe='')}?{urlencode(scope_to_query_pairs(unfiltered_scope))}")
        raw = await afetch_json_or_none(self._client, self._http, path)
        if raw is None:
            return None
        return _to_atomic_memory(raw, unfiltered_scope)

    async def delete(self, id: str, scope: MemoryScope) -> None:
        unfiltered_scope = strip_read_filters(scope)
        path = self._route(f"/memories/{quote(id, safe='')}?{urlencode(scope_to_query_pairs(unfiltered_scope))}")
        try:
            await afetch_void(self._client, self._http, path, method="DELETE")
        except ProviderError as exc:
            if exc.status_code == 404:
                return
            raise

    async def _post_ingest(
        self,
        path: str,
        input: AtomicMemoryIngestInput,
        scope: MemoryScope,
        *,
        skip_extraction: bool = False,
    ) -> AtomicMemoryIngestResult:
        assert_scope_allows_visibility(scope, input.visibility)
        body: dict[str, Any] = {
            **scope_to_fields(scope, include_thread=True),
            "conversation": input.conversation,
            "source_site": input.source_site,
            "source_url": input.source_url or "",
        }
        if isinstance(scope, WorkspaceScope) and input.visibility:
            body["visibility"] = input.visibility
        if input.config_override is not None:
            body["config_override"] = input.config_override
        if skip_extraction:
            body["skip_extraction"] = True
        raw = await afetch_json(self._client, self._http, path, method="POST", json=body)
        return AtomicMemoryIngestResult.model_validate(raw)

    async def _post_search(
        self,
        path: str,
        request: AtomicMemorySearchRequest,
        scope: MemoryScope,
    ) -> AtomicMemorySearchResultPage:
        body: dict[str, Any] = {
            **scope_to_fields(scope, include_agent_scope=True, include_thread=True),
            "query": request.query,
        }
        if request.limit is not None:
            body["limit"] = request.limit
        if request.threshold is not None:
            body["threshold"] = request.threshold
        if request.as_of is not None:
            body["as_of"] = request.as_of.isoformat()
        if request.retrieval_mode is not None:
            body["retrieval_mode"] = request.retrieval_mode
        if request.token_budget is not None:
            body["token_budget"] = request.token_budget
        if request.namespace_scope is not None:
            body["namespace_scope"] = request.namespace_scope
        if request.source_site is not None:
            body["source_site"] = request.source_site
        if request.skip_repair:
            body["skip_repair"] = True
        if request.config_override is not None:
            body["config_override"] = request.config_override
        raw = await afetch_json(self._client, self._http, path, method="POST", json=body)
        return _map_search_response(raw, scope)
