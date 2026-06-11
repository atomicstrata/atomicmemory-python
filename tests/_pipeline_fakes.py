"""Recording fakes for pipeline hook-order tests (sync + async).

Pattern mirrors tests/_lifecycle_fakes.py: one minimal provider that records
calls, plus hook factories that append (hook_name, args) tuples to a shared
log so tests assert exact invocation order and arguments.
"""

from __future__ import annotations

from typing import Any

from atomicmemory.memory.pipeline import (
    AsyncMemoryProcessingPipeline,
    MemoryProcessingPipeline,
)
from atomicmemory.memory.provider import BaseAsyncMemoryProvider, BaseMemoryProvider
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    AsyncProviderRegistry,
    ProviderRegistration,
    ProviderRegistry,
)
from atomicmemory.memory.service import (
    AsyncMemoryService,
    MemoryService,
    MemoryServiceConfig,
)
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
    ContextPackage,
    IngestInput,
    IngestResult,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    PackageRequest,
    Scope,
    SearchRequest,
    SearchResultPage,
)


class RecordingProvider(BaseMemoryProvider):
    """Records do_* calls with canned results. Built on the REAL abstract surface.

    BaseMemoryProvider defines NO __init__ and its abstract methods are the
    do_* hooks (provider.py:196-212) — overriding the public ingest/search
    wrappers would bypass _run_operation (scope validation + error wrapping).
    Mirrors tests/memory/test_service.py's _Recorder, including the package
    extension exposure.
    """

    name = "recording"

    def __init__(self, ingest_results: list[IngestResult] | None = None) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._ingest_results = list(ingest_results or [])

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(package=True),
        )

    def do_ingest(self, input: IngestInput) -> IngestResult:
        self.calls.append(("ingest", input))
        if self._ingest_results:
            return self._ingest_results.pop(0)
        return IngestResult(created=[f"mem_{len(self.calls)}"])

    def do_search(self, request: SearchRequest) -> SearchResultPage:
        self.calls.append(("search", request))
        return SearchResultPage(results=[])

    def do_get(self, ref: MemoryRef) -> Memory | None:
        self.calls.append(("get", ref))
        return None

    def do_delete(self, ref: MemoryRef) -> None:
        self.calls.append(("delete", ref))

    def do_list(self, request: ListRequest) -> ListResultPage:
        self.calls.append(("list", request))
        return ListResultPage()

    def package(self, request: PackageRequest) -> ContextPackage:
        self.calls.append(("package", request))
        return ContextPackage(text="", results=[], tokens=0, budget_constrained=False)


# Used in tests so _run_operation's scope validation passes.
_SCOPE = Scope(user="u")


def _make_service(
    provider: RecordingProvider,
    pipeline: MemoryProcessingPipeline,
) -> MemoryService:
    """Build a MemoryService with one named provider and a given pipeline."""
    registry = ProviderRegistry()
    registry.register(
        "recording",
        lambda _cfg: ProviderRegistration(provider=provider, pipeline=pipeline),
    )
    service = MemoryService(MemoryServiceConfig(default_provider="recording", provider_configs={"recording": {}}))
    service.initialize(registry)
    return service


class AsyncRecordingProvider(BaseAsyncMemoryProvider):
    """Async twin of RecordingProvider: records do_* calls with canned results."""

    name = "async-recording"

    def __init__(self, ingest_results: list[IngestResult] | None = None) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._ingest_results = list(ingest_results or [])

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(package=True),
        )

    async def do_ingest(self, input: IngestInput) -> IngestResult:
        self.calls.append(("ingest", input))
        if self._ingest_results:
            return self._ingest_results.pop(0)
        return IngestResult(created=[f"mem_{len(self.calls)}"])

    async def do_search(self, request: SearchRequest) -> SearchResultPage:
        self.calls.append(("search", request))
        return SearchResultPage(results=[])

    async def do_get(self, ref: MemoryRef) -> Memory | None:
        self.calls.append(("get", ref))
        return None

    async def do_delete(self, ref: MemoryRef) -> None:
        self.calls.append(("delete", ref))

    async def do_list(self, request: ListRequest) -> ListResultPage:
        self.calls.append(("list", request))
        return ListResultPage()

    async def package(self, request: PackageRequest) -> ContextPackage:
        self.calls.append(("package", request))
        return ContextPackage(text="", results=[], tokens=0, budget_constrained=False)


async def _make_async_service(
    provider: AsyncRecordingProvider,
    pipeline: AsyncMemoryProcessingPipeline,
) -> AsyncMemoryService:
    """Build an AsyncMemoryService with one named provider and a given pipeline."""
    registry = AsyncProviderRegistry()
    registry.register(
        "async-recording",
        lambda _cfg: AsyncProviderRegistration(provider=provider, pipeline=pipeline),
    )
    service = AsyncMemoryService(
        MemoryServiceConfig(default_provider="async-recording", provider_configs={"async-recording": {}})
    )
    await service.initialize(registry)
    return service
