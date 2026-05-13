"""Async Mem0Provider — V3 core + Health.

Async counterpart of :class:`Mem0Provider`. Same capabilities; same
verbatim-rejection invariant; same body builders.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.provider import BaseAsyncMemoryProvider
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
    HealthStatus,
    IngestInput,
    IngestResult,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    SearchRequest,
    SearchResultPage,
)
from atomicmemory.providers.mem0.config import Mem0ProviderConfig
from atomicmemory.providers.mem0.http import (
    HttpOptions,
    adelete_ignore_404,
    afetch_json,
    afetch_json_or_none,
)
from atomicmemory.providers.mem0.mappers import (
    build_ingest_body,
    build_search_body,
    resolve_infer_flag,
    to_ingest_result,
    to_memory,
    to_search_result,
    unwrap_mem0_array,
)

_logger = logging.getLogger("atomicmemory.providers.mem0")


class AsyncMem0Provider(BaseAsyncMemoryProvider):
    """Async HTTP-backed V3 provider for Mem0."""

    name = "mem0"

    def __init__(self, config: Mem0ProviderConfig) -> None:
        self._config = config
        self._http_options = HttpOptions(
            api_url=config.api_url.rstrip("/"),
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self._prefix = config.path_prefix
        self._client: httpx.AsyncClient | None = None
        self._initialized = False
        # Hold strong refs to background tasks so the event loop's weak
        # reference doesn't garbage-collect them mid-flight (RUF006).
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient()
        self._initialized = True

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    async def do_ingest(self, input: IngestInput) -> IngestResult:
        if input.mode == "verbatim":
            raise ProviderError(
                "mem0 does not support verbatim ingest; use the atomicmemory provider for "
                "deterministic one-input-equals-one-memory storage.",
                provider=self.name,
                context={"operation": "ingest", "mode": "verbatim"},
            )
        user_id = input.scope.user or ""
        body = build_ingest_body(input, user_id, self._config)
        should_defer = self._config.defer_inference and resolve_infer_flag(input, self._config)
        if should_defer:
            body["infer"] = False
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            self._path("/memories/"),
            method="POST",
            json=body,
        )
        memories = unwrap_mem0_array(raw)
        if should_defer:
            task = asyncio.create_task(self._fire_background_inference(body))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        return to_ingest_result(memories)

    async def do_search(self, request: SearchRequest) -> SearchResultPage:
        body = build_search_body(request.query, request.scope, self._config, request.limit)
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            self._search_path(),
            method="POST",
            json=body,
        )
        results = [to_search_result(m, request.scope) for m in unwrap_mem0_array(raw)]
        return SearchResultPage(results=results)

    async def do_get(self, ref: MemoryRef) -> Memory | None:
        raw = await afetch_json_or_none(self._require_client(), self._http_options, self._path(f"/memories/{ref.id}/"))
        if raw is None:
            return None
        return to_memory(raw, ref.scope)

    async def do_delete(self, ref: MemoryRef) -> None:
        await adelete_ignore_404(self._require_client(), self._http_options, self._path(f"/memories/{ref.id}/"))

    async def do_list(self, request: ListRequest) -> ListResultPage:
        limit = request.limit if request.limit is not None else 20
        offset = int(request.cursor) if request.cursor else 0
        page = (offset // limit) + 1 if offset > 0 else None
        path = self._path(f"/memories/?user_id={request.scope.user or ''}&page_size={limit}")
        if page is not None:
            path += f"&page={page}"
        raw = await afetch_json(self._require_client(), self._http_options, path)
        memories = [to_memory(m, request.scope) for m in unwrap_mem0_array(raw)]
        next_offset = offset + len(memories)
        cursor = str(next_offset) if len(memories) == limit else None
        return ListResultPage(memories=memories, cursor=cursor)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text", "messages"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(health=True),
        )

    def get_extension(self, name: str) -> Any | None:
        if name == "health":
            return self
        return None

    async def health(self) -> HealthStatus:
        start = time.monotonic()
        try:
            await afetch_json(
                self._require_client(),
                self._http_options,
                self._path("/memories/?user_id=health-check&page_size=1"),
            )
            return HealthStatus(ok=True, latency_ms=(time.monotonic() - start) * 1000.0)
        except (ProviderError, ValueError):
            return HealthStatus(ok=False, latency_ms=(time.monotonic() - start) * 1000.0)

    def _path(self, endpoint: str) -> str:
        return f"{self._prefix}{endpoint}"

    def _search_path(self) -> str:
        return "/memories/search/" if self._prefix == "" else "/v2/memories/search/"

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ProviderError(
                "AsyncMem0Provider is not initialized. Call await initialize() first.",
                provider=self.name,
            )
        return self._client

    async def _fire_background_inference(self, body: dict[str, Any]) -> None:
        try:
            await afetch_json(
                self._require_client(),
                self._http_options,
                self._path("/memories/"),
                method="POST",
                json={**body, "infer": True},
            )
        except Exception as exc:
            _logger.warning("[mem0] deferred AUDN failed: %s", exc)
