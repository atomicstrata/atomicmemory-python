"""Provider routing service.

Port of `atomicmemory-sdk/src/memory/memory-service.ts`. Provides one
sync `MemoryService` and one async `AsyncMemoryService`. Each owns the
provider→pipeline map, dispatches calls to the named (or default)
provider, and synthesizes the V3 ``package`` extension from
provider.get_extension.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atomicmemory.core.errors import ConfigError, ProviderError
from atomicmemory.memory.pipeline import NOOP_PIPELINE, MemoryProcessingPipeline
from atomicmemory.memory.provider import (
    BaseAsyncMemoryProvider,
    BaseMemoryProvider,
)
from atomicmemory.memory.registry import (
    AsyncProviderRegistry,
    ProviderRegistry,
    default_async_registry,
    default_registry,
)
from atomicmemory.memory.types import (
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


@dataclass
class MemoryServiceConfig:
    """Inputs to construct a service."""

    default_provider: str
    provider_configs: dict[str, Any]


class _ServiceBase:
    """Shared state + lookup helpers for sync and async services."""

    def __init__(self, config: MemoryServiceConfig) -> None:
        if not config.provider_configs:
            raise ConfigError("MemoryService requires at least one provider config")
        if config.default_provider not in config.provider_configs:
            raise ConfigError(f"default_provider '{config.default_provider}' is not in provider_configs")
        self._config = config
        self._default_provider_name = config.default_provider

    @property
    def default_provider_name(self) -> str:
        return self._default_provider_name

    def get_configured_providers(self) -> list[str]:
        return list(self._config.provider_configs.keys())


class MemoryService(_ServiceBase):
    """Sync provider router."""

    def __init__(self, config: MemoryServiceConfig) -> None:
        super().__init__(config)
        self._providers: dict[str, BaseMemoryProvider] = {}
        self._pipelines: dict[str, MemoryProcessingPipeline] = {}

    def initialize(self, registry: ProviderRegistry | None = None) -> None:
        reg = registry if registry is not None else default_registry
        for name, provider_config in self._config.provider_configs.items():
            factory = reg.get(name)
            if factory is None:
                continue
            registration = factory(provider_config)
            self._providers[name] = registration.provider
            self._pipelines[name] = registration.pipeline
            registration.provider.initialize()

    def close(self) -> None:
        for provider in self._providers.values():
            provider.close()

    def get_provider(self, name: str | None = None) -> BaseMemoryProvider:
        provider_name = name or self._default_provider_name
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ConfigError(f"Provider '{provider_name}' is not registered")
        return provider

    def get_available_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    def ingest(self, input: IngestInput, provider_name: str | None = None) -> IngestResult:
        provider = self.get_provider(provider_name)
        return provider.ingest(input)

    def search(self, request: SearchRequest, provider_name: str | None = None) -> SearchResultPage:
        provider = self.get_provider(provider_name)
        return provider.search(request)

    def get(self, ref: MemoryRef, provider_name: str | None = None) -> Memory | None:
        provider = self.get_provider(provider_name)
        return provider.get(ref)

    def delete(self, ref: MemoryRef, provider_name: str | None = None) -> None:
        provider = self.get_provider(provider_name)
        provider.delete(ref)

    def list(self, request: ListRequest, provider_name: str | None = None) -> ListResultPage:
        provider = self.get_provider(provider_name)
        return provider.list(request)

    def package(self, request: PackageRequest, provider_name: str | None = None) -> ContextPackage:
        provider = self.get_provider(provider_name)
        packager = provider.get_extension("package")
        if packager is None or not hasattr(packager, "package"):
            raise ProviderError(
                f"Provider '{provider.name}' does not support the 'package' extension",
                provider=provider.name,
                context={"operation": "package"},
            )
        return packager.package(request)  # type: ignore[no-any-return]

    def _pipeline(self, name: str | None) -> MemoryProcessingPipeline:
        provider_name = name or self._default_provider_name
        return self._pipelines.get(provider_name, NOOP_PIPELINE)


class AsyncMemoryService(_ServiceBase):
    """Async provider router."""

    def __init__(self, config: MemoryServiceConfig) -> None:
        super().__init__(config)
        self._providers: dict[str, BaseAsyncMemoryProvider] = {}
        self._pipelines: dict[str, MemoryProcessingPipeline] = {}

    async def initialize(self, registry: AsyncProviderRegistry | None = None) -> None:
        reg = registry if registry is not None else default_async_registry
        for name, provider_config in self._config.provider_configs.items():
            factory = reg.get(name)
            if factory is None:
                continue
            registration = factory(provider_config)
            self._providers[name] = registration.provider
            self._pipelines[name] = registration.pipeline
            await registration.provider.initialize()

    async def close(self) -> None:
        for provider in self._providers.values():
            await provider.close()

    def get_provider(self, name: str | None = None) -> BaseAsyncMemoryProvider:
        provider_name = name or self._default_provider_name
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ConfigError(f"Provider '{provider_name}' is not registered")
        return provider

    def get_available_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    async def ingest(self, input: IngestInput, provider_name: str | None = None) -> IngestResult:
        provider = self.get_provider(provider_name)
        return await provider.ingest(input)

    async def search(self, request: SearchRequest, provider_name: str | None = None) -> SearchResultPage:
        provider = self.get_provider(provider_name)
        return await provider.search(request)

    async def get(self, ref: MemoryRef, provider_name: str | None = None) -> Memory | None:
        provider = self.get_provider(provider_name)
        return await provider.get(ref)

    async def delete(self, ref: MemoryRef, provider_name: str | None = None) -> None:
        provider = self.get_provider(provider_name)
        await provider.delete(ref)

    async def list(self, request: ListRequest, provider_name: str | None = None) -> ListResultPage:
        provider = self.get_provider(provider_name)
        return await provider.list(request)

    async def package(self, request: PackageRequest, provider_name: str | None = None) -> ContextPackage:
        provider = self.get_provider(provider_name)
        packager = provider.get_extension("package")
        if packager is None or not hasattr(packager, "package"):
            raise ProviderError(
                f"Provider '{provider.name}' does not support the 'package' extension",
                provider=provider.name,
                context={"operation": "package"},
            )
        return await packager.package(request)  # type: ignore[no-any-return]
