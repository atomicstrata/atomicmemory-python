"""AsyncMemoryClient — async facade for the V3 memory layer.

Port of `atomicmemory-sdk/src/client/memory-client.ts` (async variant).
Mirrors :class:`atomicmemory.client.memory_client.MemoryClient` with
``async def`` for every I/O method and a ``__aenter__`` / ``__aexit__``
context manager. Dict coercion + Pydantic-error wrapping is identical
to the sync client.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from types import TracebackType
from typing import Any

# Importing the provider packages registers both sync and async factories.
import atomicmemory.providers.atomicmemory
import atomicmemory.providers.hindsight
import atomicmemory.providers.mem0  # noqa: F401
from atomicmemory.client.memory_client import (
    MemoryProviderConfigs,
    _coerce_ingest,
    _coerce_list_request,
    _coerce_package,
    _coerce_ref,
    _coerce_search,
    _pick_first_provider_key,
)
from atomicmemory.core.errors import ConfigError, NotInitializedError
from atomicmemory.memory.provider import BaseAsyncMemoryProvider
from atomicmemory.memory.registry import AsyncProviderRegistry, default_async_registry
from atomicmemory.memory.service import AsyncMemoryService, MemoryServiceConfig
from atomicmemory.memory.types import (
    Capabilities,
    ContextPackage,
    IngestInput,
    IngestResult,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    PackageRequest,
    SearchRequest,
    SearchResultPage,
)
from atomicmemory.providers.atomicmemory.async_handle_impl import AsyncAtomicMemoryHandle


@dataclass
class AsyncProviderStatus:
    """Async-side mirror of :class:`ProviderStatus`."""

    name: str
    initialized: bool
    capabilities: Capabilities | None


_AsyncProviderStatusList = list[AsyncProviderStatus]


class AsyncMemoryClient:
    """Async entry point for the V3 memory API.

    Example:
        >>> async with AsyncMemoryClient(
        ...     providers={"atomicmemory": {"api_url": "http://localhost:17350"}}
        ... ) as memory:
        ...     await memory.initialize()
        ...     await memory.ingest({"mode": "text", "content": "hi", "scope": {"user": "u1"}})
    """

    def __init__(
        self,
        providers: MemoryProviderConfigs,
        default_provider: str | None = None,
    ) -> None:
        if not providers:
            raise ConfigError(
                "AsyncMemoryClient requires at least one provider config. "
                'Pass e.g. {"atomicmemory": {"api_url": "..."}}.'
            )
        chosen_default = default_provider or _pick_first_provider_key(providers)
        if chosen_default is None:
            raise ConfigError("No usable provider config supplied")
        self._service = AsyncMemoryService(
            MemoryServiceConfig(
                default_provider=chosen_default,
                provider_configs=dict(providers),
            )
        )
        self._initialized = False
        self._init_error: Exception | None = None
        self._init_task: asyncio.Task[None] | None = None

    async def initialize(self, registry: AsyncProviderRegistry | None = None) -> None:
        """Initialize all configured providers. Idempotent and concurrency-safe.

        Concurrent calls on one event loop share a single initialization run
        (the first call's ``registry`` wins). The COMPLETED outcome — success
        or the original failure — is captured into loop-independent state, so
        a failed initialization is sticky from any loop: retrying re-raises
        the original error; construct a new client after resolving the cause.
        An instance is bound to the event loop of its first ``initialize()``
        while initialization is still PENDING — awaiting a pending run from a
        different loop is unsupported. ``close()`` after a SUCCESSFUL
        lifecycle returns the client to the uninitialized state.
        """
        if self._initialized:
            return
        if self._init_error is not None:
            raise self._init_error
        if self._init_task is None:
            self._init_task = asyncio.ensure_future(self._run_initialize(registry))
            self._init_task.add_done_callback(_mark_retrieved)
        task = self._init_task
        try:
            # shield: cancelling ONE waiter (e.g. wait_for timeout) must not
            # cancel the shared run for everyone — promises aren't cancellable
            # in TS, so unshielded awaiting would NOT be lifecycle parity.
            await asyncio.shield(task)
        finally:
            if task.done():
                self._init_task = None

    async def _run_initialize(self, registry: AsyncProviderRegistry | None) -> None:
        """Execute the shared initialization run; capture errors into sticky state.

        CancelledError is BaseException and never caught here, so cancellation
        never becomes sticky. A cancelled task's ``_init_task`` slot is cleared
        by a surviving waiter's ``finally`` once the task is done, or by
        ``close()``; either path lets a later call start fresh.
        """
        try:
            await self._service.initialize(registry if registry is not None else default_async_registry)
        except Exception as exc:
            self._init_error = exc
            raise
        self._initialized = True

    async def close(self) -> None:
        """Close providers; safe to call multiple times.

        Closing while an initialization is PENDING cancels that run: staged
        providers are torn down by the service's atomic-initialize cleanup,
        any concurrent initialize() waiter receives CancelledError, and the
        client ends not-initialized (no sticky error is recorded for
        cancellation). After a SUCCESSFUL lifecycle, close() returns the
        client to the uninitialized state. A FAILED initialization remains
        sticky — close() does not reset it.
        """
        task = self._init_task
        if task is not None:
            if not task.done():
                task.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await task
            # Always clear, even when already done: a run whose waiters were
            # all cancelled leaves a stale DONE task behind, and a later
            # initialize() awaiting it would resolve instantly WITHOUT
            # re-running — silently leaving the client uninitialized.
            self._init_task = None
        if not self._initialized:
            return
        try:
            await self._service.close()
        finally:
            self._initialized = False

    async def __aenter__(self) -> AsyncMemoryClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def ingest(self, input: IngestInput | dict[str, Any]) -> IngestResult:
        self._assert_initialized()
        return await self._service.ingest(_coerce_ingest(input))

    async def ingest_direct(self, input: IngestInput | dict[str, Any]) -> IngestResult:
        """Identical to :meth:`ingest`; preserved for wrapper-subclass parity with TS."""
        self._assert_initialized()
        return await self._service.ingest(_coerce_ingest(input))

    async def search(self, request: SearchRequest | dict[str, Any]) -> SearchResultPage:
        self._assert_initialized()
        return await self._service.search(_coerce_search(request))

    async def search_direct(self, request: SearchRequest | dict[str, Any]) -> SearchResultPage:
        """Identical to :meth:`search`; preserved for wrapper-subclass parity with TS."""
        self._assert_initialized()
        return await self._service.search(_coerce_search(request))

    async def package(self, request: PackageRequest | dict[str, Any]) -> ContextPackage:
        self._assert_initialized()
        return await self._service.package(_coerce_package(request))

    async def package_direct(self, request: PackageRequest | dict[str, Any]) -> ContextPackage:
        """Identical to :meth:`package`; preserved for wrapper-subclass parity with TS."""
        self._assert_initialized()
        return await self._service.package(_coerce_package(request))

    async def get(self, ref: MemoryRef | dict[str, Any]) -> Memory | None:
        self._assert_initialized()
        return await self._service.get(_coerce_ref(ref))

    async def delete(self, ref: MemoryRef | dict[str, Any]) -> None:
        self._assert_initialized()
        await self._service.delete(_coerce_ref(ref))

    async def list(self, request: ListRequest | dict[str, Any]) -> ListResultPage:
        self._assert_initialized()
        return await self._service.list(_coerce_list_request(request))

    def capabilities(self, provider_name: str | None = None) -> Capabilities:
        self._assert_initialized()
        return self._service.get_provider(provider_name).capabilities()

    def get_extension(self, extension_name: str, provider_name: str | None = None) -> Any | None:
        self._assert_initialized()
        return self._service.get_provider(provider_name).get_extension(extension_name)

    def get_provider_status(self) -> _AsyncProviderStatusList:
        configured = self._service.get_configured_providers()
        if not self._initialized:
            return [AsyncProviderStatus(name=n, initialized=False, capabilities=None) for n in configured]
        available = set(self._service.get_available_providers())
        statuses: _AsyncProviderStatusList = []
        for n in configured:
            if n not in available:
                statuses.append(AsyncProviderStatus(name=n, initialized=False, capabilities=None))
                continue
            statuses.append(
                AsyncProviderStatus(
                    name=n,
                    initialized=True,
                    capabilities=self._service.get_provider(n).capabilities(),
                )
            )
        return statuses

    def get_provider(self, name: str | None = None) -> BaseAsyncMemoryProvider:
        self._assert_initialized()
        return self._service.get_provider(name)

    @property
    def atomicmemory(self) -> AsyncAtomicMemoryHandle | None:
        """Typed access to AtomicMemory-specific routes.

        Returns ``None`` when the client is not yet initialized or the
        ``atomicmemory`` provider was not configured.
        """
        if not self._initialized:
            return None
        if "atomicmemory" not in self._service.get_configured_providers():
            return None
        provider = self._service.get_provider("atomicmemory")
        handle = provider.get_extension("atomicmemory.base")
        if not isinstance(handle, AsyncAtomicMemoryHandle):
            return None
        return handle

    def _assert_initialized(self) -> None:
        if not self._initialized:
            raise NotInitializedError("AsyncMemoryClient is not initialized. Call await client.initialize() first.")


def _mark_retrieved(task: asyncio.Task[None]) -> None:
    """Retrieve the task's exception so asyncio never logs 'never retrieved'.

    A run whose waiters were all cancelled fails unobserved; without this
    callback asyncio would log "Task exception was never retrieved" at GC.
    Correctness is unchanged: waiters still see errors through the shield,
    and stickiness is recorded by ``_run_initialize`` itself.
    """
    if not task.cancelled():
        task.exception()
