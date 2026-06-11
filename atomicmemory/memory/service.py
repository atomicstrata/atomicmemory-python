"""Provider routing service.

Port of `atomicmemory-sdk/src/memory/memory-service.ts`. Provides one
sync `MemoryService` and one async `AsyncMemoryService`. Each owns the
provider→pipeline map, dispatches calls to the named (or default)
provider, and synthesizes the V3 ``package`` extension from
provider.get_extension.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from dataclasses import dataclass
from typing import Any

from atomicmemory.core.errors import ConfigError, UnsupportedOperationError
from atomicmemory.memory.pipeline import (
    NOOP_ASYNC_PIPELINE,
    NOOP_PIPELINE,
    AsyncMemoryProcessingPipeline,
    MemoryProcessingPipeline,
)
from atomicmemory.memory.provider import (
    BaseAsyncMemoryProvider,
    BaseMemoryProvider,
)
from atomicmemory.memory.registry import (
    AsyncProviderFactory,
    AsyncProviderRegistration,
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


def _merge_ingest_results(results: list[IngestResult]) -> IngestResult:
    """Concatenate per-item ingest results in input order (mirrors TS mergeIngestResults)."""
    return IngestResult(
        created=[m for r in results for m in r.created],
        updated=[m for r in results for m in r.updated],
        unchanged=[m for r in results for m in r.unchanged],
    )


async def _resolve_async_registration(factory: AsyncProviderFactory, config: Any) -> AsyncProviderRegistration:
    """Invoke an async-registry factory, awaiting the result if it is awaitable.

    Args:
        factory: An async-registry factory; may return the registration
            directly or an awaitable of it (lazy/async construction).
        config: The provider-specific config object passed to the factory.

    Returns:
        The resolved ``AsyncProviderRegistration``.
    """
    registration = factory(config)
    # Mypy strict narrows the registration|awaitable union on BOTH branches
    # of isawaitable here, so no casts are needed to pin the return type.
    if inspect.isawaitable(registration):
        return await registration
    return registration


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
        """Initialize all configured providers atomically.

        Registrations are staged locally and committed only after every
        factory and provider ``initialize()`` succeeds, so a mid-loop failure
        never leaves partially registered providers observable. On failure,
        already-staged providers get a best-effort ``close()`` before the
        original error re-raises.
        """
        reg = registry if registry is not None else default_registry
        staged_providers: dict[str, BaseMemoryProvider] = {}
        staged_pipelines: dict[str, MemoryProcessingPipeline] = {}
        try:
            for name, provider_config in self._config.provider_configs.items():
                factory = reg.get(name)
                if factory is None:
                    continue
                registration = factory(provider_config)
                staged_providers[name] = registration.provider
                staged_pipelines[name] = registration.pipeline
                registration.provider.initialize()
            if self._default_provider_name not in staged_providers:
                raise ConfigError(f"Default provider '{self._default_provider_name}' has no factory in the registry")
        except BaseException:
            for provider in staged_providers.values():
                with contextlib.suppress(Exception):
                    provider.close()
            raise
        # REPLACE (don't update) so a close() → re-initialize with a different
        # registry can never resurrect a previously-closed provider.
        self._providers = staged_providers
        self._pipelines = staged_pipelines

    def close(self) -> None:
        """Close every provider best-effort, clear state, then re-raise the first failure.

        Only the FIRST close failure is re-raised; failures from later
        providers are suppressed after every provider has been given the
        chance to close.
        """
        first_error: Exception | None = None
        try:
            for provider in self._providers.values():
                try:
                    provider.close()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
        finally:
            self._providers = {}
            self._pipelines = {}
        if first_error is not None:
            raise first_error

    def get_provider(self, name: str | None = None) -> BaseMemoryProvider:
        provider_name = name or self._default_provider_name
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ConfigError(f"Provider '{provider_name}' is not registered")
        return provider

    def get_available_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    def ingest(self, input: IngestInput, provider_name: str | None = None) -> IngestResult:
        """Ingest through the provider's pipeline.

        ``preprocess_ingest`` may split one input into many; each per-item
        result passes through ``postprocess_ingest``; the merged result
        concatenates ``created``/``updated``/``unchanged`` in input order.
        If a per-item ingest raises mid-split, earlier items remain persisted
        and no merged result is returned, so splitting pipelines should be idempotent.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        if pipeline.preprocess_ingest is not None:
            results: list[IngestResult] = []
            for item in pipeline.preprocess_ingest(input):
                result = provider.ingest(item)
                if pipeline.postprocess_ingest is not None:
                    pipeline.postprocess_ingest(result, item)
                results.append(result)
            return _merge_ingest_results(results)
        result = provider.ingest(input)
        if pipeline.postprocess_ingest is not None:
            pipeline.postprocess_ingest(result, input)
        return result

    def search(self, request: SearchRequest, provider_name: str | None = None) -> SearchResultPage:
        """Search through the provider's pipeline.

        The PROCESSED request (after ``preprocess_search``) flows to both the
        provider and ``postprocess_search`` — never the original.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        processed = pipeline.preprocess_search(request) if pipeline.preprocess_search is not None else request
        page = provider.search(processed)
        return pipeline.postprocess_search(page, processed) if pipeline.postprocess_search is not None else page

    def get(self, ref: MemoryRef, provider_name: str | None = None) -> Memory | None:
        """Get through the provider's pipeline.

        The PROCESSED ref (after ``preprocess_get``) flows to both the
        provider and ``postprocess_get`` — never the original.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        processed = pipeline.preprocess_get(ref) if pipeline.preprocess_get is not None else ref
        memory = provider.get(processed)
        return pipeline.postprocess_get(memory, processed) if pipeline.postprocess_get is not None else memory

    def delete(self, ref: MemoryRef, provider_name: str | None = None) -> None:
        provider = self.get_provider(provider_name)
        provider.delete(ref)

    def list(self, request: ListRequest, provider_name: str | None = None) -> ListResultPage:
        """List through the provider's pipeline.

        Post-only: there is no list preprocess; the provider receives the
        ORIGINAL request, which also flows to ``postprocess_list``.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        page = provider.list(request)
        return pipeline.postprocess_list(page, request) if pipeline.postprocess_list is not None else page

    def package(self, request: PackageRequest, provider_name: str | None = None) -> ContextPackage:
        provider = self.get_provider(provider_name)
        packager = provider.get_extension("package")
        if packager is None or not hasattr(packager, "package"):
            raise UnsupportedOperationError(provider=provider.name, operation="package")
        return packager.package(request)  # type: ignore[no-any-return]

    def _pipeline(self, name: str | None) -> MemoryProcessingPipeline:
        provider_name = name or self._default_provider_name
        return self._pipelines.get(provider_name, NOOP_PIPELINE)


class AsyncMemoryService(_ServiceBase):
    """Async provider router."""

    def __init__(self, config: MemoryServiceConfig) -> None:
        super().__init__(config)
        self._providers: dict[str, BaseAsyncMemoryProvider] = {}
        self._pipelines: dict[str, AsyncMemoryProcessingPipeline] = {}

    async def initialize(self, registry: AsyncProviderRegistry | None = None) -> None:
        """Initialize all configured providers atomically.

        Factories may return the registration directly or an awaitable of it
        (enabling lazy/async provider construction). Registrations are staged
        and committed only on full success; on failure, staged providers get a
        best-effort ``close()`` before the original error re-raises.
        """
        reg = registry if registry is not None else default_async_registry
        staged_providers: dict[str, BaseAsyncMemoryProvider] = {}
        staged_pipelines: dict[str, AsyncMemoryProcessingPipeline] = {}
        try:
            for name, provider_config in self._config.provider_configs.items():
                factory = reg.get(name)
                if factory is None:
                    continue
                registration = await _resolve_async_registration(factory, provider_config)
                staged_providers[name] = registration.provider
                staged_pipelines[name] = registration.pipeline
                await registration.provider.initialize()
            if self._default_provider_name not in staged_providers:
                raise ConfigError(f"Default provider '{self._default_provider_name}' has no factory in the registry")
        except BaseException:
            await asyncio.gather(
                *(provider.close() for provider in staged_providers.values()),
                return_exceptions=True,
            )
            raise
        # REPLACE (don't update) — same stale-provider rationale as the sync service.
        self._providers = staged_providers
        self._pipelines = staged_pipelines

    async def close(self) -> None:
        """Close every provider best-effort, clear state, then re-raise the first failure.

        Only the FIRST close failure is re-raised; failures from later
        providers are suppressed after every provider has been given the
        chance to close.
        """
        first_error: Exception | None = None
        try:
            for provider in self._providers.values():
                try:
                    await provider.close()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
        finally:
            self._providers = {}
            self._pipelines = {}
        if first_error is not None:
            raise first_error

    def get_provider(self, name: str | None = None) -> BaseAsyncMemoryProvider:
        provider_name = name or self._default_provider_name
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ConfigError(f"Provider '{provider_name}' is not registered")
        return provider

    def get_available_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    # Mirrors MemoryService.ingest — keep the hook logic in sync.
    async def ingest(self, input: IngestInput, provider_name: str | None = None) -> IngestResult:
        """Ingest through the provider's pipeline.

        ``preprocess_ingest`` may split one input into many; each per-item
        result passes through ``postprocess_ingest``; the merged result
        concatenates ``created``/``updated``/``unchanged`` in input order.
        If a per-item ingest raises mid-split, earlier items remain persisted
        and no merged result is returned, so splitting pipelines should be idempotent.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        if pipeline.preprocess_ingest is not None:
            results: list[IngestResult] = []
            for item in await pipeline.preprocess_ingest(input):
                result = await provider.ingest(item)
                if pipeline.postprocess_ingest is not None:
                    await pipeline.postprocess_ingest(result, item)
                results.append(result)
            return _merge_ingest_results(results)
        result = await provider.ingest(input)
        if pipeline.postprocess_ingest is not None:
            await pipeline.postprocess_ingest(result, input)
        return result

    # Mirrors MemoryService.search — keep the hook logic in sync.
    async def search(self, request: SearchRequest, provider_name: str | None = None) -> SearchResultPage:
        """Search through the provider's pipeline.

        The PROCESSED request (after ``preprocess_search``) flows to both the
        provider and ``postprocess_search`` — never the original.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        processed = await pipeline.preprocess_search(request) if pipeline.preprocess_search is not None else request
        page = await provider.search(processed)
        if pipeline.postprocess_search is not None:
            return await pipeline.postprocess_search(page, processed)
        return page

    # Mirrors MemoryService.get — keep the hook logic in sync.
    async def get(self, ref: MemoryRef, provider_name: str | None = None) -> Memory | None:
        """Get through the provider's pipeline.

        The PROCESSED ref (after ``preprocess_get``) flows to both the
        provider and ``postprocess_get`` — never the original.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        processed = await pipeline.preprocess_get(ref) if pipeline.preprocess_get is not None else ref
        memory = await provider.get(processed)
        if pipeline.postprocess_get is not None:
            return await pipeline.postprocess_get(memory, processed)
        return memory

    # Mirrors MemoryService.delete — keep the hook logic in sync.
    async def delete(self, ref: MemoryRef, provider_name: str | None = None) -> None:
        provider = self.get_provider(provider_name)
        await provider.delete(ref)

    # Mirrors MemoryService.list — keep the hook logic in sync.
    async def list(self, request: ListRequest, provider_name: str | None = None) -> ListResultPage:
        """List through the provider's pipeline.

        Post-only: there is no list preprocess; the provider receives the
        ORIGINAL request, which also flows to ``postprocess_list``.
        """
        provider = self.get_provider(provider_name)
        pipeline = self._pipeline(provider_name)
        page = await provider.list(request)
        if pipeline.postprocess_list is not None:
            return await pipeline.postprocess_list(page, request)
        return page

    def _pipeline(self, name: str | None) -> AsyncMemoryProcessingPipeline:
        provider_name = name or self._default_provider_name
        return self._pipelines.get(provider_name, NOOP_ASYNC_PIPELINE)

    async def package(self, request: PackageRequest, provider_name: str | None = None) -> ContextPackage:
        provider = self.get_provider(provider_name)
        packager = provider.get_extension("package")
        if packager is None or not hasattr(packager, "package"):
            raise UnsupportedOperationError(provider=provider.name, operation="package")
        return await packager.package(request)  # type: ignore[no-any-return]
