"""Async HindsightProvider — V3 core plus package, reflect, and health."""

from __future__ import annotations

import time
from typing import Any

import httpx

from atomicmemory.core.errors import ProviderError
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
    Insight,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    PackageRequest,
    Scope,
    SearchRequest,
    SearchResultPage,
)
from atomicmemory.providers.hindsight.config import (
    HINDSIGHT_DEFAULT_API_VERSION,
    HINDSIGHT_DEFAULT_PROJECT_ID,
    AsyncHindsightOperationsHandle,
    AsyncHindsightRetainHandle,
    HindsightOperation,
    HindsightOperationsPage,
    HindsightProviderConfig,
    HindsightRetainResponse,
)
from atomicmemory.providers.hindsight.http import HttpOptions, adelete_ignore_404, afetch_json, afetch_json_or_none
from atomicmemory.providers.hindsight.mappers import (
    build_recall_request,
    build_retain_request,
    to_memory,
    to_search_result,
    unwrap_results,
)
from atomicmemory.providers.hindsight.provider import (
    _assert_retain_succeeded,
    _format_package_text,
    _is_healthy,
    _map_list_page,
    _normalize_operation,
    _normalize_segment,
    _to_insight,
)


class AsyncHindsightProvider(BaseAsyncMemoryProvider):
    """Async HTTP-backed V3 provider for Hindsight."""

    name = "hindsight"

    def __init__(self, config: HindsightProviderConfig) -> None:
        self._config = config
        self._http_options = HttpOptions(config.api_url.rstrip("/"), config.api_key, config.timeout_seconds)
        self._api_version = _normalize_segment(config.api_version or HINDSIGHT_DEFAULT_API_VERSION)
        self._project_id = _normalize_segment(config.project_id or HINDSIGHT_DEFAULT_PROJECT_ID)
        self._client: httpx.AsyncClient | None = None
        self._initialized = False
        self._retain_handle = AsyncHindsightRetainHandle(self._retain_extension)
        self._operations_handle = AsyncHindsightOperationsHandle(
            self._list_operations_extension,
            self._get_operation_extension,
        )

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
                "hindsight does not support verbatim ingest.",
                provider=self.name,
                context={"operation": "ingest", "mode": "verbatim"},
            )
        await self._retain(input)
        return IngestResult(created=[], updated=[], unchanged=[])

    async def do_search(self, request: SearchRequest) -> SearchResultPage:
        raw = await self._recall_raw(request)
        results = [to_search_result(row, request.scope) for row in unwrap_results(raw)]
        if request.limit is not None:
            results = results[: request.limit]
        return SearchResultPage(results=results)

    async def do_get(self, ref: MemoryRef) -> Memory | None:
        raw = await afetch_json_or_none(
            self._require_client(), self._http_options, self._memory_path(ref.scope, ref.id)
        )
        return to_memory(raw, ref.scope) if isinstance(raw, dict) else None

    async def do_delete(self, ref: MemoryRef) -> None:
        await adelete_ignore_404(self._require_client(), self._http_options, self._memory_path(ref.scope, ref.id))

    async def do_list(self, request: ListRequest) -> ListResultPage:
        from urllib.parse import urlencode

        limit = request.limit or 20
        offset = int(request.cursor) if request.cursor else 0
        query = urlencode({"limit": str(limit), "offset": str(offset)})
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(request.scope)}/memories/list?{query}",
        )
        return _map_list_page(raw, request.scope, offset, limit)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text", "messages"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(package=True, reflect=True, health=True),
            custom_extensions={
                "hindsight.retain": CustomExtensionMeta(
                    version="1.0.0",
                    description="Raw Hindsight retain response and operation metadata.",
                ),
                "hindsight.operations": CustomExtensionMeta(
                    version="1.0.0",
                    description="Hindsight async operation status helpers.",
                ),
            },
        )

    def get_extension(self, name: str) -> Any | None:
        if name == "hindsight.retain":
            return self._retain_handle
        if name == "hindsight.operations":
            return self._operations_handle
        if name in {"package", "reflect", "health"}:
            return self
        return None

    async def package(self, request: PackageRequest) -> ContextPackage:
        return await self._run_operation("package", request.scope, lambda: self._package(request))

    async def reflect(self, query: str, scope: Scope) -> list[Insight]:
        return await self._run_operation("reflect", scope, lambda: self._reflect(query, scope))

    async def _package(self, request: PackageRequest) -> ContextPackage:
        raw = await self._recall_raw(request, request.token_budget)
        results = [to_search_result(row, request.scope) for row in unwrap_results(raw)]
        text = _format_package_text([result.memory for result in results])
        from atomicmemory.providers.hindsight.mappers import estimate_tokens

        return ContextPackage(text=text, results=results, tokens=estimate_tokens(text), budget_constrained=False)

    async def _reflect(self, query: str, scope: Scope) -> list[Insight]:
        from atomicmemory.providers.hindsight.mappers import build_reflect_request

        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(scope)}/reflect",
            method="POST",
            json=build_reflect_request(query, scope),
        )
        return [_to_insight(raw)]

    async def health(self) -> HealthStatus:
        start = time.monotonic()
        try:
            raw = await afetch_json(self._require_client(), self._http_options, "/health")
            return HealthStatus(
                ok=_is_healthy(raw),
                latency_ms=(time.monotonic() - start) * 1000.0,
                version=raw.get("version") if isinstance(raw.get("version"), str) else None,
            )
        except (ProviderError, ValueError):
            return HealthStatus(ok=False, latency_ms=(time.monotonic() - start) * 1000.0)

    async def _retain_extension(self, input: IngestInput) -> HindsightRetainResponse:
        return await self._run_operation("hindsight.retain", input.scope, lambda: self._retain(input))

    async def _list_operations_extension(self, scope: Scope) -> HindsightOperationsPage:
        return await self._run_operation("hindsight.operations", scope, lambda: self._list_operations(scope))

    async def _get_operation_extension(self, scope: Scope, operation_id: str) -> HindsightOperation | None:
        return await self._run_operation(
            "hindsight.operations", scope, lambda: self._get_operation(scope, operation_id)
        )

    async def _retain(self, input: IngestInput) -> HindsightRetainResponse:
        raw = await afetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(input.scope)}/memories",
            method="POST",
            json=build_retain_request(input),
        )
        retained = HindsightRetainResponse.model_validate(raw)
        _assert_retain_succeeded(retained)
        return retained

    async def _recall_raw(self, request: SearchRequest, max_tokens: int | None = None) -> Any:
        return await afetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(request.scope)}/memories/recall",
            method="POST",
            json=build_recall_request(request.query, request.scope, self._config, max_tokens),
        )

    async def _list_operations(self, scope: Scope) -> HindsightOperationsPage:
        raw = await afetch_json(self._require_client(), self._http_options, f"{self._bank_path(scope)}/operations")
        return HindsightOperationsPage.model_validate(raw)

    async def _get_operation(self, scope: Scope, operation_id: str) -> HindsightOperation | None:
        from urllib.parse import quote

        raw = await afetch_json_or_none(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(scope)}/operations/{quote(operation_id, safe='')}",
        )
        return _normalize_operation(raw) if isinstance(raw, dict) else None

    def _bank_path(self, scope: Scope) -> str:
        from urllib.parse import quote

        from atomicmemory.providers.hindsight.mappers import bank_id_for_scope

        return self._route(f"/banks/{quote(bank_id_for_scope(scope), safe='')}")

    def _memory_path(self, scope: Scope, memory_id: str) -> str:
        from urllib.parse import quote

        return f"{self._bank_path(scope)}/memories/{quote(memory_id, safe='')}"

    def _route(self, path: str) -> str:
        return f"/{self._api_version}/{self._project_id}{path}"

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ProviderError(
                "AsyncHindsightProvider is not initialized. Call await initialize() first.", provider=self.name
            )
        return self._client
