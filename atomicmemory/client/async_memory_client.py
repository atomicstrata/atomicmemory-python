"""AsyncMemoryClient — async facade for the V3 memory layer.

Mirrors :class:`atomicmemory.client.memory_client.MemoryClient` with
``async def`` for every I/O method and a ``__aenter__`` / ``__aexit__``
context manager. Dict coercion + Pydantic-error wrapping is identical
to the sync client.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any

# Importing the provider packages registers both sync and async factories.
import atomicmemory.providers.atomicmemory
import atomicmemory.providers.mem0  # noqa: F401
from atomicmemory.client.memory_client import (
    _coerce_ingest,
    _coerce_list_request,
    _coerce_package,
    _coerce_ref,
    _coerce_search,
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

MemoryProviderConfigs = dict[str, Any]


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
        ...     providers={"atomicmemory": {"api_url": "http://localhost:3050"}}
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

    async def initialize(self, registry: AsyncProviderRegistry | None = None) -> None:
        if self._initialized:
            return
        await self._service.initialize(registry if registry is not None else default_async_registry)
        self._initialized = True

    async def close(self) -> None:
        if not self._initialized:
            return
        await self._service.close()
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
        self._assert_initialized()
        return await self._service.ingest(_coerce_ingest(input))

    async def search(self, request: SearchRequest | dict[str, Any]) -> SearchResultPage:
        self._assert_initialized()
        return await self._service.search(_coerce_search(request))

    async def search_direct(self, request: SearchRequest | dict[str, Any]) -> SearchResultPage:
        self._assert_initialized()
        return await self._service.search(_coerce_search(request))

    async def package(self, request: PackageRequest | dict[str, Any]) -> ContextPackage:
        self._assert_initialized()
        return await self._service.package(_coerce_package(request))

    async def package_direct(self, request: PackageRequest | dict[str, Any]) -> ContextPackage:
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


def _pick_first_provider_key(providers: MemoryProviderConfigs) -> str | None:
    for key, value in providers.items():
        if value is not None and key != "default":
            return key
    return None
