"""Async AtomicMemoryProvider — V3 core + Packager + TemporalSearch + Versioner + Health.

Async counterpart of `provider.py`. Uses :class:`httpx.AsyncClient` and
the ``a*`` HTTP helpers; body construction is delegated to the shared
private builders defined alongside the sync provider.

The ``atomicmemory.*`` handle namespace is wired in
``async_handle_impl.py``; this module owns provider lifecycle + the
``do_*`` overrides on :class:`BaseAsyncMemoryProvider`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.meta_fact_filter import filter_meta_facts
from atomicmemory.memory.provider import BaseAsyncMemoryProvider
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
    ContextPackage,
    CustomExtensionMeta,
    HealthStatus,
    IngestInput,
    IngestResult,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    MemoryVersion,
    PackageRequest,
    SearchRequest,
    SearchResult,
    SearchResultPage,
)
from atomicmemory.providers.atomicmemory.async_handle_impl import AsyncAtomicMemoryHandle
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.handle import ATOMICMEMORY_EXTENSION_NAMES
from atomicmemory.providers.atomicmemory.http import (
    HttpOptions,
    adelete_ignore_404,
    afetch_json,
    afetch_json_or_none,
)
from atomicmemory.providers.atomicmemory.mappers import (
    to_ingest_result,
    to_memory,
    to_memory_version,
    to_retrieval_receipt,
    to_search_result,
)
from atomicmemory.providers.atomicmemory.path import normalize_api_version
from atomicmemory.providers.atomicmemory.provider import (
    _build_ingest_body,
    _build_list_path,
    _build_package_body,
    _build_search_body,
    _qs,
)

_ATOMICMEMORY_CUSTOM_EXTENSIONS: dict[str, CustomExtensionMeta] = {
    name: CustomExtensionMeta(version="1.0.0") for name in ATOMICMEMORY_EXTENSION_NAMES
}


class AsyncAtomicMemoryProvider(BaseAsyncMemoryProvider):
    """Async HTTP-backed V3 provider for atomicmemory-core."""

    name = "atomicmemory"

    def __init__(self, config: AtomicMemoryProviderConfig) -> None:
        self._config = config
        self._http_options = HttpOptions(
            api_url=config.api_url.rstrip("/"),
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self._api_prefix = normalize_api_version(config.api_version)
        self._client: httpx.AsyncClient | None = None
        self._handle: AsyncAtomicMemoryHandle | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient()
        if self._handle is None:
            self._handle = AsyncAtomicMemoryHandle(self._client, self._http_options, self._route)
        self._initialized = True

    async def close(self) -> None:
        self._handle = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    # ------------------------------------------------------------------
    # V3 core methods
    # ------------------------------------------------------------------

    async def do_ingest(self, input: IngestInput) -> IngestResult:
        body = _build_ingest_body(input)
        path = self._route("/memories/ingest/quick" if input.mode == "verbatim" else "/memories/ingest")
        raw = await afetch_json(self._require_client(), self._http_options, path, method="POST", json=body)
        return to_ingest_result(raw)

    def _apply_meta_fact_filter(self, results: list[SearchResult]) -> list[SearchResult]:
        """Drop meta-facts when the opt-in filter is enabled; otherwise pass through."""
        config = self._config.meta_fact_filter
        if config is None or not config.enabled:
            return results
        return filter_meta_facts(results, lambda result: result.memory.content, config)

    async def do_search(self, request: SearchRequest) -> SearchResultPage:
        body = _build_search_body(request)
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            self._route("/memories/search/fast"),
            method="POST",
            json=body,
        )
        return SearchResultPage(
            results=self._apply_meta_fact_filter([to_search_result(m, request.scope) for m in raw.get("memories", [])]),
            retrieval=to_retrieval_receipt(raw["retrieval"]) if raw.get("retrieval") else None,
        )

    async def do_get(self, ref: MemoryRef) -> Memory | None:
        path = self._route(f"/memories/{ref.id}?user_id={_qs(ref.scope.user)}")
        raw = await afetch_json_or_none(self._require_client(), self._http_options, path)
        if raw is None:
            return None
        return to_memory(raw, ref.scope)

    async def do_delete(self, ref: MemoryRef) -> None:
        path = self._route(f"/memories/{ref.id}?user_id={_qs(ref.scope.user)}")
        await adelete_ignore_404(self._require_client(), self._http_options, path)

    async def do_list(self, request: ListRequest) -> ListResultPage:
        offset = int(request.cursor) if request.cursor else 0
        limit = request.limit if request.limit is not None else 20
        path = self._route(_build_list_path(request.scope, limit, offset))
        raw = await afetch_json(self._require_client(), self._http_options, path)
        memories = [to_memory(m, request.scope) for m in raw.get("memories", [])]
        next_offset = offset + len(memories)
        cursor = str(next_offset) if len(memories) == limit else None
        return ListResultPage(memories=memories, cursor=cursor)

    # ------------------------------------------------------------------
    # Capabilities + extension dispatch
    # ------------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text", "messages", "verbatim"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(
                package=True,
                temporal=True,
                versioning=True,
                health=True,
            ),
            custom_extensions=_ATOMICMEMORY_CUSTOM_EXTENSIONS,
        )

    def get_extension(self, name: str) -> Any | None:
        if name in {"package", "temporal", "versioning", "health"}:
            return self
        if name == "atomicmemory.base":
            return self._handle
        if name == "atomicmemory.lifecycle" and self._handle is not None:
            return self._handle.lifecycle
        if name == "atomicmemory.audit" and self._handle is not None:
            return self._handle.audit
        if name == "atomicmemory.lessons" and self._handle is not None:
            return self._handle.lessons
        if name == "atomicmemory.config" and self._handle is not None:
            return self._handle.config
        if name == "atomicmemory.agents" and self._handle is not None:
            return self._handle.agents
        return None

    # ------------------------------------------------------------------
    # V3 extensions implemented inline
    # ------------------------------------------------------------------

    async def package(self, request: PackageRequest) -> ContextPackage:
        body = _build_package_body(request)
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            self._route("/memories/search"),
            method="POST",
            json=body,
        )
        results: list[SearchResult] = self._apply_meta_fact_filter(
            [to_search_result(m, request.scope) for m in raw.get("memories", [])]
        )
        budget_constrained = raw.get("budget_constrained")
        if not isinstance(budget_constrained, bool):
            raise ValueError(
                "atomicmemory async provider.package: backend response missing required boolean "
                "field `budget_constrained`"
            )
        return ContextPackage(
            text=raw.get("injection_text") or "",
            results=results,
            tokens=raw.get("estimated_context_tokens") or 0,
            budget_constrained=budget_constrained,
        )

    async def search_as_of(self, request: SearchRequest, as_of: datetime) -> SearchResultPage:
        body = _build_search_body(request)
        body["as_of"] = as_of.isoformat()
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            self._route("/memories/search"),
            method="POST",
            json=body,
        )
        return SearchResultPage(
            results=self._apply_meta_fact_filter([to_search_result(m, request.scope) for m in raw.get("memories", [])]),
            retrieval=to_retrieval_receipt(raw["retrieval"]) if raw.get("retrieval") else None,
        )

    async def history(self, ref: MemoryRef) -> list[MemoryVersion]:
        path = self._route(f"/memories/{ref.id}/audit?user_id={_qs(ref.scope.user)}")
        raw = await afetch_json(self._require_client(), self._http_options, path)
        return [to_memory_version(entry) for entry in raw.get("trail", [])]

    async def health(self) -> HealthStatus:
        path = self._route("/memories/health")
        raw = await afetch_json(self._require_client(), self._http_options, path)
        return HealthStatus(ok=raw.get("status") == "ok")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _route(self, path: str) -> str:
        return f"{self._api_prefix}{path}"

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ProviderError(
                "AsyncAtomicMemoryProvider is not initialized. Call initialize() first.",
                provider=self.name,
            )
        return self._client
