"""Sync HindsightProvider — V3 core plus package, reflect, and health."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from atomicmemory.core.errors import ProviderError
from atomicmemory.memory.provider import BaseMemoryProvider
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
    HindsightOperation,
    HindsightOperationsHandle,
    HindsightOperationsPage,
    HindsightProviderConfig,
    HindsightRetainHandle,
    HindsightRetainResponse,
)
from atomicmemory.providers.hindsight.http import HttpOptions, delete_ignore_404, fetch_json, fetch_json_or_none
from atomicmemory.providers.hindsight.mappers import (
    bank_id_for_scope,
    build_recall_request,
    build_reflect_request,
    build_retain_request,
    estimate_tokens,
    to_memory,
    to_search_result,
    unwrap_results,
)


class HindsightProvider(BaseMemoryProvider):
    """HTTP-backed V3 provider for Hindsight Cloud or self-hosted Hindsight."""

    name = "hindsight"

    def __init__(self, config: HindsightProviderConfig) -> None:
        self._config = config
        self._http_options = HttpOptions(
            api_url=config.api_url.rstrip("/"),
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self._api_version = _normalize_segment(config.api_version or HINDSIGHT_DEFAULT_API_VERSION)
        self._project_id = _normalize_segment(config.project_id or HINDSIGHT_DEFAULT_PROJECT_ID)
        self._client: httpx.Client | None = None
        self._initialized = False
        self._retain_handle = HindsightRetainHandle(self._retain_extension)
        self._operations_handle = HindsightOperationsHandle(
            self._list_operations_extension, self._get_operation_extension
        )

    def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.Client()
        self._initialized = True

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._initialized = False

    def do_ingest(self, input: IngestInput) -> IngestResult:
        if input.mode == "verbatim":
            raise ProviderError(
                "hindsight does not support verbatim ingest.",
                provider=self.name,
                context={"operation": "ingest", "mode": "verbatim"},
            )
        self._retain(input)
        return IngestResult(created=[], updated=[], unchanged=[])

    def do_search(self, request: SearchRequest) -> SearchResultPage:
        raw = self._recall_raw(request)
        results = [to_search_result(row, request.scope) for row in unwrap_results(raw)]
        if request.limit is not None:
            results = results[: request.limit]
        return SearchResultPage(results=results)

    def do_get(self, ref: MemoryRef) -> Memory | None:
        raw = fetch_json_or_none(self._require_client(), self._http_options, self._memory_path(ref.scope, ref.id))
        return to_memory(raw, ref.scope) if isinstance(raw, dict) else None

    def do_delete(self, ref: MemoryRef) -> None:
        delete_ignore_404(self._require_client(), self._http_options, self._memory_path(ref.scope, ref.id))

    def do_list(self, request: ListRequest) -> ListResultPage:
        limit = request.limit or 20
        offset = int(request.cursor) if request.cursor else 0
        query = urlencode({"limit": str(limit), "offset": str(offset)})
        raw = fetch_json(
            self._require_client(), self._http_options, f"{self._bank_path(request.scope)}/memories/list?{query}"
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

    def package(self, request: PackageRequest) -> ContextPackage:
        return self._run_operation("package", request.scope, lambda: self._package(request))

    def reflect(self, query: str, scope: Scope) -> list[Insight]:
        return self._run_operation("reflect", scope, lambda: self._reflect(query, scope))

    def health(self) -> HealthStatus:
        start = time.monotonic()
        try:
            raw = fetch_json(self._require_client(), self._http_options, "/health")
            return HealthStatus(
                ok=_is_healthy(raw),
                latency_ms=(time.monotonic() - start) * 1000.0,
                version=raw.get("version") if isinstance(raw.get("version"), str) else None,
            )
        except (ProviderError, ValueError):
            return HealthStatus(ok=False, latency_ms=(time.monotonic() - start) * 1000.0)

    def _package(self, request: PackageRequest) -> ContextPackage:
        raw = self._recall_raw(request, request.token_budget)
        results = [to_search_result(row, request.scope) for row in unwrap_results(raw)]
        text = _format_package_text([result.memory for result in results])
        return ContextPackage(
            text=text,
            results=results,
            tokens=estimate_tokens(text),
            budget_constrained=False,
        )

    def _reflect(self, query: str, scope: Scope) -> list[Insight]:
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(scope)}/reflect",
            method="POST",
            json=build_reflect_request(query, scope),
        )
        return [_to_insight(raw)]

    def _retain_extension(self, input: IngestInput) -> HindsightRetainResponse:
        return self._run_operation("hindsight.retain", input.scope, lambda: self._retain(input))

    def _list_operations_extension(self, scope: Scope) -> HindsightOperationsPage:
        return self._run_operation("hindsight.operations", scope, lambda: self._list_operations(scope))

    def _get_operation_extension(self, scope: Scope, operation_id: str) -> HindsightOperation | None:
        return self._run_operation("hindsight.operations", scope, lambda: self._get_operation(scope, operation_id))

    def _retain(self, input: IngestInput) -> HindsightRetainResponse:
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(input.scope)}/memories",
            method="POST",
            json=build_retain_request(input),
        )
        retained = HindsightRetainResponse.model_validate(raw)
        _assert_retain_succeeded(retained)
        return retained

    def _recall_raw(self, request: SearchRequest, max_tokens: int | None = None) -> Any:
        return fetch_json(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(request.scope)}/memories/recall",
            method="POST",
            json=build_recall_request(request.query, request.scope, self._config, max_tokens),
        )

    def _list_operations(self, scope: Scope) -> HindsightOperationsPage:
        raw = fetch_json(self._require_client(), self._http_options, f"{self._bank_path(scope)}/operations")
        return HindsightOperationsPage.model_validate(raw)

    def _get_operation(self, scope: Scope, operation_id: str) -> HindsightOperation | None:
        raw = fetch_json_or_none(
            self._require_client(),
            self._http_options,
            f"{self._bank_path(scope)}/operations/{quote(operation_id, safe='')}",
        )
        return _normalize_operation(raw) if isinstance(raw, dict) else None

    def _bank_path(self, scope: Scope) -> str:
        return self._route(f"/banks/{quote(bank_id_for_scope(scope), safe='')}")

    def _memory_path(self, scope: Scope, memory_id: str) -> str:
        return f"{self._bank_path(scope)}/memories/{quote(memory_id, safe='')}"

    def _route(self, path: str) -> str:
        return f"/{self._api_version}/{self._project_id}{path}"

    def _require_client(self) -> httpx.Client:
        if self._client is None:
            raise ProviderError("HindsightProvider is not initialized. Call initialize() first.", provider=self.name)
        return self._client


def _normalize_segment(segment: str) -> str:
    return segment.strip("/")


def _map_list_page(raw: Any, scope: Scope, offset: int, limit: int) -> ListResultPage:
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError("Hindsight list response missing items array")
    total = raw.get("total")
    if not isinstance(total, int):
        raise ValueError("Hindsight list response missing total")
    rows = list(raw["items"])
    next_offset = offset + len(rows)
    cursor = str(next_offset) if next_offset < total else None
    return ListResultPage(memories=[to_memory(row, scope) for row in rows], cursor=cursor)


def _assert_retain_succeeded(raw: HindsightRetainResponse) -> None:
    if raw.success is False:
        raise ProviderError(
            f"Hindsight retain failed: {_retain_failure_context(raw)}",
            provider="hindsight",
            context={"operation": "ingest"},
        )


def _retain_failure_context(raw: HindsightRetainResponse) -> str:
    ids = ",".join(raw.operation_ids or []) or raw.operation_id or "none"
    return f"operation_id={ids}, items_count={raw.items_count or 'unknown'}, async={raw.async_}"


def _normalize_operation(raw: dict[str, Any]) -> HindsightOperation:
    return HindsightOperation(
        id=str(raw["operation_id"]),
        task_type=raw.get("operation_type"),
        created_at=raw.get("created_at"),
        status=raw.get("status"),
        error_message=raw.get("error_message"),
        retry_count=raw.get("retry_count"),
        next_retry_at=raw.get("next_retry_at"),
    )


def _format_package_text(memories: list[Memory]) -> str:
    if not memories:
        return ""
    lines = [f"- [{_package_type_label(memory)}] {memory.content}" for memory in memories]
    return "\n".join(["Relevant memories:", *lines])


def _package_type_label(memory: Memory) -> str:
    hindsight_type = memory.metadata.get("hindsightType") if memory.metadata else None
    return str(hindsight_type or memory.kind or "memory")


def _to_insight(raw: Any) -> Insight:
    if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
        raise ValueError("Hindsight reflect response missing text")
    return Insight(content=raw["text"], confidence=0.0, supporting_memory_ids=_supporting_ids(raw))


def _supporting_ids(raw: dict[str, Any]) -> list[str]:
    based_on = raw.get("based_on")
    memories = based_on.get("memories") if isinstance(based_on, dict) else None
    if not isinstance(memories, list):
        return []
    return [item["id"] for item in memories if isinstance(item, dict) and isinstance(item.get("id"), str)]


def _is_healthy(raw: Any) -> bool:
    if not isinstance(raw, dict):
        raise ValueError("Hindsight health response must be an object")
    if isinstance(raw.get("ok"), bool):
        return bool(raw["ok"])
    return raw.get("status") in {None, "ok", "healthy"}
