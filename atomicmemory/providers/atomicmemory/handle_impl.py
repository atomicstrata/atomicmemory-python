"""AtomicMemoryHandle root implementation — base routes + categories.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/handle-impl.ts:78-191`
plus the namespace-specific memory/search mappers (lines 321-463).

This module owns the base 8 routes (ingestFull, ingestQuick, search,
searchFast, expand, list, get, delete) and exposes the five category
sub-handles. Per-category modules live alongside.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from atomicmemory.core.errors import ProviderError, ValidationError
from atomicmemory.providers.atomicmemory.agents import AtomicMemoryAgents
from atomicmemory.providers.atomicmemory.audit import AtomicMemoryAudit
from atomicmemory.providers.atomicmemory.config_handle import AtomicMemoryConfig
from atomicmemory.providers.atomicmemory.handle import (
    AtomicMemoryIngestInput,
    AtomicMemoryIngestResult,
    AtomicMemoryListOptions,
    AtomicMemoryListResultPage,
    AtomicMemoryMemory,
    AtomicMemorySearchRequest,
    AtomicMemorySearchResult,
    AtomicMemorySearchResultPage,
    MemoryScope,
    WorkspaceScope,
)
from atomicmemory.providers.atomicmemory.http import HttpOptions, fetch_json, fetch_json_or_none, fetch_void
from atomicmemory.providers.atomicmemory.lessons import AtomicMemoryLessons
from atomicmemory.providers.atomicmemory.lifecycle import AtomicMemoryLifecycle
from atomicmemory.providers.atomicmemory.scope_mapper import (
    assert_scope_allows_visibility,
    scope_to_fields,
    scope_to_query_pairs,
    strip_agent_scope,
)

Route = Callable[[str], str]


class AtomicMemoryHandle:
    """Typed access to AtomicMemory-specific routes.

    Constructed by :class:`AtomicMemoryProvider` and exposed via
    ``MemoryClient.atomicmemory``. Base routes hang off this object;
    category handles hang off ``.lifecycle``, ``.audit``, ``.lessons``,
    ``.config``, ``.agents``.
    """

    def __init__(self, client: httpx.Client, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route
        self.lifecycle = AtomicMemoryLifecycle(client, http, route)
        self.audit = AtomicMemoryAudit(client, http, route)
        self.lessons = AtomicMemoryLessons(client, http, route)
        self.config = AtomicMemoryConfig(client, http, route)
        self.agents = AtomicMemoryAgents(client, http, route)

    # ------------------------------------------------------------------
    # Base routes
    # ------------------------------------------------------------------

    def ingest_full(self, input: AtomicMemoryIngestInput, scope: MemoryScope) -> AtomicMemoryIngestResult:
        return self._post_ingest(self._route("/memories/ingest"), input, scope)

    def ingest_quick(
        self,
        input: AtomicMemoryIngestInput,
        scope: MemoryScope,
        skip_extraction: bool = False,
    ) -> AtomicMemoryIngestResult:
        return self._post_ingest(self._route("/memories/ingest/quick"), input, scope, skip_extraction=skip_extraction)

    def search(self, request: AtomicMemorySearchRequest, scope: MemoryScope) -> AtomicMemorySearchResultPage:
        return self._post_search(self._route("/memories/search"), request, scope)

    def search_fast(self, request: AtomicMemorySearchRequest, scope: MemoryScope) -> AtomicMemorySearchResultPage:
        # Core's fast-search handler parses `as_of` but drops it; we still
        # send it for forward-compat per TS handle-impl.
        return self._post_search(self._route("/memories/search/fast"), request, scope)

    def expand(self, refs: list[str], scope: MemoryScope) -> list[AtomicMemoryMemory]:
        body: dict[str, Any] = {**scope_to_fields(scope), "memory_ids": refs}
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/expand"),
            method="POST",
            json=body,
        )
        echoed = strip_agent_scope(scope)
        return [_to_atomic_memory(m, echoed) for m in raw.get("memories", [])]

    def list(
        self,
        scope: MemoryScope,
        options: AtomicMemoryListOptions | dict[str, Any] | None = None,
    ) -> AtomicMemoryListResultPage:
        opts = _coerce_list_options(options)
        _assert_list_options_scope_compat(scope, opts)
        pairs: list[tuple[str, str]] = scope_to_query_pairs(scope)
        if opts.limit is not None:
            pairs.append(("limit", str(opts.limit)))
        if opts.offset is not None:
            pairs.append(("offset", str(opts.offset)))
        if opts.source_site:
            pairs.append(("source_site", opts.source_site))
        if opts.episode_id:
            pairs.append(("episode_id", opts.episode_id))
        path = self._route(f"/memories/list?{urlencode(pairs)}")
        raw = fetch_json(self._client, self._http, path)
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

    def get(self, id: str, scope: MemoryScope) -> AtomicMemoryMemory | None:
        path = self._route(f"/memories/{quote(id, safe='')}?{urlencode(scope_to_query_pairs(scope))}")
        raw = fetch_json_or_none(self._client, self._http, path)
        if raw is None:
            return None
        return _to_atomic_memory(raw, strip_agent_scope(scope))

    def delete(self, id: str, scope: MemoryScope) -> None:
        path = self._route(f"/memories/{quote(id, safe='')}?{urlencode(scope_to_query_pairs(scope))}")
        try:
            fetch_void(self._client, self._http, path, method="DELETE")
        except ProviderError as exc:
            if exc.status_code == 404:
                return
            raise

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _post_ingest(
        self,
        path: str,
        input: AtomicMemoryIngestInput,
        scope: MemoryScope,
        *,
        skip_extraction: bool = False,
    ) -> AtomicMemoryIngestResult:
        assert_scope_allows_visibility(scope, input.visibility)
        body: dict[str, Any] = {
            **scope_to_fields(scope),
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
        raw = fetch_json(self._client, self._http, path, method="POST", json=body)
        return AtomicMemoryIngestResult.model_validate(raw)

    def _post_search(
        self,
        path: str,
        request: AtomicMemorySearchRequest,
        scope: MemoryScope,
    ) -> AtomicMemorySearchResultPage:
        body: dict[str, Any] = {
            **scope_to_fields(scope, include_agent_scope=True),
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
        raw = fetch_json(self._client, self._http, path, method="POST", json=body)
        return _map_search_response(raw, scope)


# ---------------------------------------------------------------------------
# Mapping helpers (namespace-specific; do NOT reuse V3's mappers)
# ---------------------------------------------------------------------------


def _coerce_list_options(
    options: AtomicMemoryListOptions | dict[str, Any] | None,
) -> AtomicMemoryListOptions:
    if options is None:
        return AtomicMemoryListOptions()
    if isinstance(options, dict):
        return AtomicMemoryListOptions.model_validate(options)
    return options


def _assert_list_options_scope_compat(scope: MemoryScope, options: AtomicMemoryListOptions) -> None:
    """Reject options core silently drops on workspace lists.

    ``source_site`` and ``episode_id`` are user-scope only. Core
    ignores them on workspace lists *but still validates* episode_id as
    a UUID before branching, which can surface as a misleading 400.
    Fail closed in the SDK so the mismatch surfaces at the call site.
    """
    if not isinstance(scope, WorkspaceScope):
        return
    if options.source_site is not None:
        raise ValidationError(
            "`source_site` is only valid on user scope; core ignores it on "
            "workspace list queries. Omit the option or use a user-scope list.",
            context={"scope_kind": "workspace"},
        )
    if options.episode_id is not None:
        raise ValidationError(
            "`episode_id` is only valid on user scope; core ignores it on "
            "workspace list queries but still validates it as a UUID first. "
            "Omit the option or use a user-scope list.",
            context={"scope_kind": "workspace"},
        )


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _to_atomic_memory(raw: dict[str, Any], scope: MemoryScope) -> AtomicMemoryMemory:
    """Map raw core memory to AtomicMemoryMemory, preserving full scope.

    Distinct from V3's ``to_memory`` which flattens scope to a `Scope`
    and drops ``importance`` into metadata. The namespace surface keeps
    those as first-class fields.
    """
    payload: dict[str, Any] = {
        "id": raw["id"],
        "content": raw.get("content") or "",
        "scope": scope,
        "created_at": _parse_iso(raw.get("created_at")) or _now_utc(),
    }
    if raw.get("updated_at"):
        payload["updated_at"] = _parse_iso(raw["updated_at"])
    for field in ("importance", "source_site", "source_url", "episode_id", "visibility", "metadata"):
        if raw.get(field) is not None:
            payload[field] = raw[field]
    return AtomicMemoryMemory.model_validate(payload)


def _to_atomic_search_result(raw: dict[str, Any], scope: MemoryScope) -> AtomicMemorySearchResult:
    similarity = _coalesce(raw.get("semantic_similarity"), raw.get("similarity"))
    ranking_score = _coalesce(raw.get("ranking_score"), raw.get("score"))
    relevance = raw.get("relevance")
    score = _coalesce(ranking_score, similarity, 0.0)
    payload: dict[str, Any] = {
        "memory": _to_atomic_memory(raw, scope),
        "score": score,
    }
    if similarity is not None:
        payload["similarity"] = similarity
    if ranking_score is not None:
        payload["ranking_score"] = ranking_score
    if relevance is not None:
        payload["relevance"] = relevance
    if raw.get("importance") is not None:
        payload["importance"] = raw["importance"]
    return AtomicMemorySearchResult.model_validate(payload)


def _map_search_response(raw: dict[str, Any], scope: MemoryScope) -> AtomicMemorySearchResultPage:
    memories_raw = raw.get("memories") or []
    payload: dict[str, Any] = {
        "count": raw.get("count", len(memories_raw)),
        "retrieval_mode": raw.get("retrieval_mode") or "flat",
        "scope": scope,
        "results": [_to_atomic_search_result(m, scope) for m in memories_raw],
    }
    if raw.get("injection_text") is not None:
        payload["injection_text"] = raw["injection_text"]
    for field in ("citations", "tier_assignments", "expand_ids", "lesson_check", "consensus", "observability"):
        if raw.get(field) is not None:
            payload[field] = raw[field]
    if raw.get("estimated_context_tokens") is not None:
        payload["estimated_context_tokens"] = raw["estimated_context_tokens"]
    return AtomicMemorySearchResultPage.model_validate(payload)


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def _now_utc() -> datetime:
    from datetime import timezone

    return datetime.now(tz=timezone.utc)
