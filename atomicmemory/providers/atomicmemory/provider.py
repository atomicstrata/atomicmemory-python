"""Sync AtomicMemoryProvider — V3 core methods + Packager + TemporalSearch + Versioner + Health.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/atomicmemory-provider.ts`.
The handle namespace (lifecycle/audit/lessons/config/agents) is wired via
:mod:`atomicmemory.providers.atomicmemory.handle_impl`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

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
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    MemoryVersion,
    PackageFormat,
    PackageRequest,
    SearchRequest,
    SearchResult,
    SearchResultPage,
)
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.handle import ATOMICMEMORY_EXTENSION_NAMES
from atomicmemory.providers.atomicmemory.handle_impl import AtomicMemoryHandle
from atomicmemory.providers.atomicmemory.http import (
    HttpOptions,
    delete_ignore_404,
    fetch_json,
    fetch_json_or_none,
)
from atomicmemory.providers.atomicmemory.mappers import (
    to_ingest_result,
    to_memory,
    to_memory_version,
    to_search_result,
)
from atomicmemory.providers.atomicmemory.path import normalize_api_version

_ATOMICMEMORY_CUSTOM_EXTENSIONS: dict[str, CustomExtensionMeta] = {
    name: CustomExtensionMeta(version="1.0.0") for name in ATOMICMEMORY_EXTENSION_NAMES
}


class AtomicMemoryProvider(BaseMemoryProvider):
    """Sync HTTP-backed V3 provider for atomicmemory-core."""

    name = "atomicmemory"

    def __init__(self, config: AtomicMemoryProviderConfig) -> None:
        self._config = config
        self._http_options = HttpOptions(
            api_url=config.api_url.rstrip("/"),
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self._api_prefix = normalize_api_version(config.api_version)
        self._client: httpx.Client | None = None
        self._handle: AtomicMemoryHandle | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.Client()
        if self._handle is None:
            self._handle = AtomicMemoryHandle(self._client, self._http_options, self._route)
        self._initialized = True

    def close(self) -> None:
        self._handle = None
        if self._client is not None:
            self._client.close()
            self._client = None
        self._initialized = False

    # ------------------------------------------------------------------
    # V3 core methods
    # ------------------------------------------------------------------

    def do_ingest(self, input: IngestInput) -> IngestResult:
        body = _build_ingest_body(input)
        path = self._route("/memories/ingest/quick" if input.mode == "verbatim" else "/memories/ingest")
        raw = fetch_json(self._require_client(), self._http_options, path, method="POST", json=body)
        return to_ingest_result(raw)

    def do_search(self, request: SearchRequest) -> SearchResultPage:
        body = _build_search_body(request)
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            self._route("/memories/search/fast"),
            method="POST",
            json=body,
        )
        return SearchResultPage(
            results=[to_search_result(m, request.scope) for m in raw.get("memories", [])],
        )

    def do_get(self, ref: MemoryRef) -> Memory | None:
        path = self._route(f"/memories/{ref.id}?user_id={_qs(ref.scope.user)}")
        raw = fetch_json_or_none(self._require_client(), self._http_options, path)
        if raw is None:
            return None
        return to_memory(raw, ref.scope)

    def do_delete(self, ref: MemoryRef) -> None:
        path = self._route(f"/memories/{ref.id}?user_id={_qs(ref.scope.user)}")
        delete_ignore_404(self._require_client(), self._http_options, path)

    def do_list(self, request: ListRequest) -> ListResultPage:
        offset = int(request.cursor) if request.cursor else 0
        limit = request.limit if request.limit is not None else 20
        path = self._route(f"/memories/list?user_id={_qs(request.scope.user)}&limit={limit}&offset={offset}")
        raw = fetch_json(self._require_client(), self._http_options, path)
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
    # V3 extensions implemented inline (`Packager`, `TemporalSearch`,
    # `Versioner`, `Health`)
    # ------------------------------------------------------------------

    def package(self, request: PackageRequest) -> ContextPackage:
        body = _build_package_body(request)
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            self._route("/memories/search"),
            method="POST",
            json=body,
        )
        results: list[SearchResult] = [to_search_result(m, request.scope) for m in raw.get("memories", [])]
        budget_constrained = raw.get("budget_constrained")
        if not isinstance(budget_constrained, bool):
            raise ValueError(
                "atomicmemory provider.package: backend response missing required boolean field `budget_constrained`"
            )
        return ContextPackage(
            text=raw.get("injection_text") or "",
            results=results,
            tokens=raw.get("estimated_context_tokens") or 0,
            budget_constrained=budget_constrained,
        )

    def search_as_of(self, request: SearchRequest, as_of: datetime) -> SearchResultPage:
        body = _build_search_body(request)
        body["as_of"] = as_of.isoformat()
        raw = fetch_json(
            self._require_client(),
            self._http_options,
            self._route("/memories/search"),
            method="POST",
            json=body,
        )
        return SearchResultPage(
            results=[to_search_result(m, request.scope) for m in raw.get("memories", [])],
        )

    def history(self, ref: MemoryRef) -> list[MemoryVersion]:
        path = self._route(f"/memories/{ref.id}/audit?user_id={_qs(ref.scope.user)}")
        raw = fetch_json(self._require_client(), self._http_options, path)
        return [to_memory_version(entry) for entry in raw.get("trail", [])]

    def health(self) -> HealthStatus:
        path = self._route("/memories/health")
        raw = fetch_json(self._require_client(), self._http_options, path)
        return HealthStatus(ok=raw.get("status") == "ok")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _route(self, path: str) -> str:
        return f"{self._api_prefix}{path}"

    def _require_client(self) -> httpx.Client:
        if self._client is None:
            raise ProviderError(
                "AtomicMemoryProvider is not initialized. Call initialize() first.",
                provider=self.name,
            )
        return self._client


# ---------------------------------------------------------------------------
# Body builders — pure functions shared with the async provider.
# ---------------------------------------------------------------------------


_PACKAGE_FORMAT_TO_RETRIEVAL_MODE: dict[PackageFormat, str] = {
    "flat": "flat",
    "tiered": "tiered",
    "structured": "abstract-aware",
}


def _ingest_input_to_conversation(input: IngestInput) -> str:
    match input.mode:
        case "text" | "verbatim":
            return input.content
        case "messages":
            return "\n".join(f"{m.role}: {m.content}" for m in input.messages)


def _build_ingest_body(input: IngestInput) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": input.scope.user,
        "conversation": _ingest_input_to_conversation(input),
        "source_site": input.provenance.source if input.provenance and input.provenance.source else "sdk",
        "source_url": input.provenance.source_url if input.provenance and input.provenance.source_url else "",
    }
    if input.mode == "verbatim":
        body["skip_extraction"] = True
        if input.metadata:
            body["metadata"] = input.metadata
    return body


def _build_search_body(request: SearchRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": request.scope.user,
        "query": request.query,
    }
    if request.limit is not None:
        body["limit"] = request.limit
    if request.threshold is not None:
        body["threshold"] = request.threshold
    if request.scope.namespace is not None:
        body["namespace_scope"] = request.scope.namespace
    return body


def _build_package_body(request: PackageRequest) -> dict[str, Any]:
    body = _build_search_body(request)
    if request.format is not None:
        body["retrieval_mode"] = _PACKAGE_FORMAT_TO_RETRIEVAL_MODE[request.format]
    if request.token_budget is not None:
        body["token_budget"] = request.token_budget
    body["skip_repair"] = True
    return body


def _qs(value: str | None) -> str:
    """URL-encode a query-string value; empty string when falsy."""
    return quote(value, safe="") if value else ""
