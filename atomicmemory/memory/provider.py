"""V3 memory provider interface and base classes (sync + async).

Port of `atomicmemory-sdk/src/memory/provider.ts`. Defines the
``MemoryProvider`` interface, every standard V3 extension Protocol, and
two abstract base classes — one sync, one async — that share scope
validation, ready-state enforcement, and error wrapping.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol, TypeVar, runtime_checkable

from atomicmemory.core.errors import InvalidScopeError, NotInitializedError, ProviderError, ValidationError
from atomicmemory.memory.types import (
    Capabilities,
    ContextPackage,
    GraphResult,
    GraphSearchRequest,
    HealthStatus,
    IngestInput,
    IngestResult,
    Insight,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    MemoryVersion,
    PackageRequest,
    Profile,
    Scope,
    SearchRequest,
    SearchResultPage,
)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Standard extension Protocols (sync + async)
# ---------------------------------------------------------------------------


@runtime_checkable
class Updater(Protocol):
    def update(self, ref: MemoryRef, content: str) -> Memory: ...


@runtime_checkable
class AsyncUpdater(Protocol):
    async def update(self, ref: MemoryRef, content: str) -> Memory: ...


@runtime_checkable
class Packager(Protocol):
    def package(self, request: PackageRequest) -> ContextPackage: ...


@runtime_checkable
class AsyncPackager(Protocol):
    async def package(self, request: PackageRequest) -> ContextPackage: ...


@runtime_checkable
class TemporalSearch(Protocol):
    def search_as_of(self, request: SearchRequest, as_of: datetime) -> SearchResultPage: ...


@runtime_checkable
class AsyncTemporalSearch(Protocol):
    async def search_as_of(self, request: SearchRequest, as_of: datetime) -> SearchResultPage: ...


@runtime_checkable
class GraphSearch(Protocol):
    def search_graph(self, request: GraphSearchRequest) -> GraphResult: ...


@runtime_checkable
class AsyncGraphSearch(Protocol):
    async def search_graph(self, request: GraphSearchRequest) -> GraphResult: ...


@runtime_checkable
class Forgetter(Protocol):
    def forget(self, ref: MemoryRef, reason: str | None = None) -> None: ...


@runtime_checkable
class AsyncForgetter(Protocol):
    async def forget(self, ref: MemoryRef, reason: str | None = None) -> None: ...


@runtime_checkable
class Profiler(Protocol):
    def profile(self, scope: Scope, instructions: list[str] | None = None) -> Profile: ...


@runtime_checkable
class AsyncProfiler(Protocol):
    async def profile(self, scope: Scope, instructions: list[str] | None = None) -> Profile: ...


@runtime_checkable
class Reflector(Protocol):
    def reflect(self, query: str, scope: Scope) -> list[Insight]: ...


@runtime_checkable
class AsyncReflector(Protocol):
    async def reflect(self, query: str, scope: Scope) -> list[Insight]: ...


@runtime_checkable
class Versioner(Protocol):
    def history(self, ref: MemoryRef) -> list[MemoryVersion]: ...


@runtime_checkable
class AsyncVersioner(Protocol):
    async def history(self, ref: MemoryRef) -> list[MemoryVersion]: ...


@runtime_checkable
class BatchOps(Protocol):
    def batch_ingest(self, inputs: list[IngestInput]) -> list[IngestResult]: ...
    def batch_delete(self, refs: list[MemoryRef]) -> None: ...


@runtime_checkable
class AsyncBatchOps(Protocol):
    async def batch_ingest(self, inputs: list[IngestInput]) -> list[IngestResult]: ...
    async def batch_delete(self, refs: list[MemoryRef]) -> None: ...


@runtime_checkable
class Health(Protocol):
    def health(self) -> HealthStatus: ...


@runtime_checkable
class AsyncHealth(Protocol):
    async def health(self) -> HealthStatus: ...


# ---------------------------------------------------------------------------
# Shared scope validation
# ---------------------------------------------------------------------------


def _missing_scope_fields(scope: Scope, required: list[str]) -> list[str]:
    """Return required fields that are missing/empty on ``scope``."""
    missing: list[str] = []
    for field in required:
        value = getattr(scope, field, None)
        if not value:
            missing.append(field)
    return missing


# Operations whose name conflicts with a Python builtin/keyword and is
# stored under a trailing-underscore field name on the model.
_OPERATION_FIELD_OVERRIDES: dict[str, str] = {"list": "list_"}


def _required_for(capabilities: Capabilities, operation: str) -> list[str]:
    """Look up the required-scope list for ``operation``.

    Falls back to ``capabilities.required_scope.default`` when the
    operation has no override.
    """
    field = _OPERATION_FIELD_OVERRIDES.get(operation, operation)
    op_specific: list[str] | None = getattr(capabilities.required_scope, field, None)
    if op_specific is not None:
        return op_specific
    return capabilities.required_scope.default


# ---------------------------------------------------------------------------
# Sync base class
# ---------------------------------------------------------------------------


class BaseMemoryProvider(ABC):
    """Sync abstract base for synchronous V3 memory providers.

    Subclasses implement the ``do_*`` hooks; this base wires
    ready-state, scope validation, and error normalization through
    ``_run_operation``.
    """

    name: str = ""
    _initialized: bool = True

    @abstractmethod
    def do_ingest(self, input: IngestInput) -> IngestResult: ...

    @abstractmethod
    def do_search(self, request: SearchRequest) -> SearchResultPage: ...

    @abstractmethod
    def do_get(self, ref: MemoryRef) -> Memory | None: ...

    @abstractmethod
    def do_delete(self, ref: MemoryRef) -> None: ...

    @abstractmethod
    def do_list(self, request: ListRequest) -> ListResultPage: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    def initialize(self) -> None:  # noqa: B027 — override-or-pass is intentional
        """Optional async setup hook. Default is a no-op."""

    def close(self) -> None:  # noqa: B027 — override-or-pass is intentional
        """Optional teardown hook. Default is a no-op."""

    def ingest(self, input: IngestInput) -> IngestResult:
        return self._run_operation("ingest", input.scope, lambda: self.do_ingest(input))

    def search(self, request: SearchRequest) -> SearchResultPage:
        return self._run_operation("search", request.scope, lambda: self.do_search(request))

    def get(self, ref: MemoryRef) -> Memory | None:
        return self._run_operation("get", ref.scope, lambda: self.do_get(ref))

    def delete(self, ref: MemoryRef) -> None:
        self._run_operation("delete", ref.scope, lambda: self.do_delete(ref))

    def list(self, request: ListRequest) -> ListResultPage:
        return self._run_operation("list", request.scope, lambda: self.do_list(request))

    def get_extension(self, name: str) -> Any | None:
        return self._resolve_extension(name)

    def _resolve_extension(self, name: str) -> Any | None:
        caps = self.capabilities()
        if getattr(caps.extensions, name, False):
            return self
        return None

    def _run_operation(
        self,
        operation: str,
        scope: Scope | None,
        fn: Callable[[], T],
    ) -> T:
        self._assert_ready()
        if scope is not None:
            self._validate_scope(scope, operation)
        try:
            return fn()
        except (ProviderError, ValidationError, NotInitializedError):
            raise
        except Exception as exc:
            raise ProviderError(str(exc), provider=self.name, context={"operation": operation}) from exc

    def _assert_ready(self) -> None:
        if not self._initialized:
            raise NotInitializedError(f"{self.name} is not initialized. Call initialize() first.")

    def _validate_scope(self, scope: Scope, operation: str) -> None:
        required = _required_for(self.capabilities(), operation)
        if not required:
            return
        missing = _missing_scope_fields(scope, required)
        if missing:
            raise InvalidScopeError(self.name, missing, operation)


# ---------------------------------------------------------------------------
# Async base class
# ---------------------------------------------------------------------------


class BaseAsyncMemoryProvider(ABC):
    """Async abstract base for asynchronous V3 memory providers."""

    name: str = ""
    _initialized: bool = True

    @abstractmethod
    async def do_ingest(self, input: IngestInput) -> IngestResult: ...

    @abstractmethod
    async def do_search(self, request: SearchRequest) -> SearchResultPage: ...

    @abstractmethod
    async def do_get(self, ref: MemoryRef) -> Memory | None: ...

    @abstractmethod
    async def do_delete(self, ref: MemoryRef) -> None: ...

    @abstractmethod
    async def do_list(self, request: ListRequest) -> ListResultPage: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    async def initialize(self) -> None:  # noqa: B027 — override-or-pass is intentional
        """Optional async setup hook. Default is a no-op."""

    async def close(self) -> None:  # noqa: B027 — override-or-pass is intentional
        """Optional async teardown hook. Default is a no-op."""

    async def ingest(self, input: IngestInput) -> IngestResult:
        return await self._run_operation("ingest", input.scope, lambda: self.do_ingest(input))

    async def search(self, request: SearchRequest) -> SearchResultPage:
        return await self._run_operation("search", request.scope, lambda: self.do_search(request))

    async def get(self, ref: MemoryRef) -> Memory | None:
        return await self._run_operation("get", ref.scope, lambda: self.do_get(ref))

    async def delete(self, ref: MemoryRef) -> None:
        await self._run_operation("delete", ref.scope, lambda: self.do_delete(ref))

    async def list(self, request: ListRequest) -> ListResultPage:
        return await self._run_operation("list", request.scope, lambda: self.do_list(request))

    def get_extension(self, name: str) -> Any | None:
        return self._resolve_extension(name)

    def _resolve_extension(self, name: str) -> Any | None:
        caps = self.capabilities()
        if getattr(caps.extensions, name, False):
            return self
        return None

    async def _run_operation(
        self,
        operation: str,
        scope: Scope | None,
        fn: Callable[[], Awaitable[T]],
    ) -> T:
        self._assert_ready()
        if scope is not None:
            self._validate_scope(scope, operation)
        try:
            return await fn()
        except (ProviderError, ValidationError, NotInitializedError):
            raise
        except Exception as exc:
            raise ProviderError(str(exc), provider=self.name, context={"operation": operation}) from exc

    def _assert_ready(self) -> None:
        if not self._initialized:
            raise NotInitializedError(f"{self.name} is not initialized. Call initialize() first.")

    def _validate_scope(self, scope: Scope, operation: str) -> None:
        required = _required_for(self.capabilities(), operation)
        if not required:
            return
        missing = _missing_scope_fields(scope, required)
        if missing:
            raise InvalidScopeError(self.name, missing, operation)


# Type alias for any provider — useful for client/service signatures that
# don't care which flavor.
MemoryProvider = BaseMemoryProvider
AsyncMemoryProvider = BaseAsyncMemoryProvider

__all__ = [
    "AsyncBatchOps",
    "AsyncForgetter",
    "AsyncGraphSearch",
    "AsyncHealth",
    "AsyncMemoryProvider",
    "AsyncPackager",
    "AsyncProfiler",
    "AsyncReflector",
    "AsyncTemporalSearch",
    "AsyncUpdater",
    "AsyncVersioner",
    "BaseAsyncMemoryProvider",
    "BaseMemoryProvider",
    "BatchOps",
    "Forgetter",
    "GraphSearch",
    "Health",
    "MemoryProvider",
    "Packager",
    "Profiler",
    "Reflector",
    "TemporalSearch",
    "Updater",
    "Versioner",
]
