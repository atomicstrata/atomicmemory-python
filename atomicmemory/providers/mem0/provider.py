"""Sync Mem0Provider — V3 core + Health.

Port of `atomicmemory-sdk/src/memory/mem0-provider/mem0-provider.ts`.
Mem0's ``/memories`` endpoint always runs server-side extraction, so
``verbatim`` ingest is rejected — capabilities advertise only
``text`` + ``messages`` modes, and ``do_ingest`` raises
``ProviderError("Unsupported")`` if a verbatim input slips through.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.provider import BaseMemoryProvider
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
    delete_ignore_404,
    fetch_json,
    fetch_json_or_none,
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


class Mem0Provider(BaseMemoryProvider):
    """Sync HTTP-backed V3 provider for Mem0 (OSS + hosted)."""

    name = "mem0"

    def __init__(self, config: Mem0ProviderConfig) -> None:
        self._config = config
        self._http_options = HttpOptions(
            api_url=config.api_url.rstrip("/"),
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self._prefix = config.path_prefix
        self._client: httpx.Client | None = None
        self._initialized = False

    def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.Client()
        self._initialized = True

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._initialized = False

    # ------------------------------------------------------------------
    # V3 core methods
    # ------------------------------------------------------------------

    def do_ingest(self, input: IngestInput) -> IngestResult:
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
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            self._path("/memories/"),
            method="POST",
            json=body,
        )
        memories = unwrap_mem0_array(raw)
        if should_defer:
            self._fire_background_inference(body)
        return to_ingest_result(memories)

    def do_search(self, request: SearchRequest) -> SearchResultPage:
        body = build_search_body(request.query, request.scope, self._config, request.limit)
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            self._search_path(),
            method="POST",
            json=body,
        )
        results = [to_search_result(m, request.scope) for m in unwrap_mem0_array(raw)]
        return SearchResultPage(results=results)

    def do_get(self, ref: MemoryRef) -> Memory | None:
        raw = fetch_json_or_none(self._require_client(), self._http_options, self._path(f"/memories/{ref.id}/"))
        if raw is None:
            return None
        return to_memory(raw, ref.scope)

    def do_delete(self, ref: MemoryRef) -> None:
        delete_ignore_404(self._require_client(), self._http_options, self._path(f"/memories/{ref.id}/"))

    def do_list(self, request: ListRequest) -> ListResultPage:
        limit = request.limit if request.limit is not None else 20
        offset = int(request.cursor) if request.cursor else 0
        page = (offset // limit) + 1 if offset > 0 else None
        path = self._path(f"/memories/?user_id={request.scope.user or ''}&page_size={limit}")
        if page is not None:
            path += f"&page={page}"
        raw = fetch_json(self._require_client(), self._http_options, path)
        memories = [to_memory(m, request.scope) for m in unwrap_mem0_array(raw)]
        next_offset = offset + len(memories)
        cursor = str(next_offset) if len(memories) == limit else None
        return ListResultPage(memories=memories, cursor=cursor)

    # ------------------------------------------------------------------
    # Capabilities + extensions
    # ------------------------------------------------------------------

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

    def health(self) -> HealthStatus:
        start = time.monotonic()
        try:
            fetch_json(
                self._require_client(),
                self._http_options,
                self._path("/memories/?user_id=health-check&page_size=1"),
            )
            return HealthStatus(ok=True, latency_ms=(time.monotonic() - start) * 1000.0)
        except (ProviderError, ValueError):
            return HealthStatus(ok=False, latency_ms=(time.monotonic() - start) * 1000.0)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _path(self, endpoint: str) -> str:
        return f"{self._prefix}{endpoint}"

    def _search_path(self) -> str:
        # mem0 2.0 split search out of the v1 family.
        return "/memories/search/" if self._prefix == "" else "/v2/memories/search/"

    def _require_client(self) -> httpx.Client:
        if self._client is None:
            raise ProviderError(
                "Mem0Provider is not initialized. Call initialize() first.",
                provider=self.name,
            )
        return self._client

    def _fire_background_inference(self, body: dict[str, Any]) -> None:
        """Best-effort re-ingest with infer=true. Errors are logged, never raised."""
        try:
            fetch_json(
                self._require_client(),
                self._http_options,
                self._path("/memories/"),
                method="POST",
                json={**body, "infer": True},
            )
        except Exception as exc:
            _logger.warning("[mem0] deferred AUDN failed: %s", exc)
