"""Provider registry — name → factory mapping.

Port of `atomicmemory-sdk/src/memory/providers/registry.ts`. Concrete
provider modules register themselves here so the client can wire them
up by name from a config dict.

Two registries live side-by-side: one for sync providers and one for
async providers. Each maps a provider name (e.g. ``"atomicmemory"``,
``"mem0"``) to a factory that takes the provider's config object and
returns a `ProviderRegistration`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from atomicmemory.memory.pipeline import NOOP_PIPELINE, MemoryProcessingPipeline
from atomicmemory.memory.provider import (
    BaseAsyncMemoryProvider,
    BaseMemoryProvider,
)


@dataclass(frozen=True)
class ProviderRegistration:
    """Result of a provider factory call."""

    provider: BaseMemoryProvider
    pipeline: MemoryProcessingPipeline = NOOP_PIPELINE


@dataclass(frozen=True)
class AsyncProviderRegistration:
    """Async counterpart of `ProviderRegistration`."""

    provider: BaseAsyncMemoryProvider
    pipeline: MemoryProcessingPipeline = NOOP_PIPELINE


SyncProviderFactory = Callable[[Any], ProviderRegistration]
AsyncProviderFactory = Callable[[Any], AsyncProviderRegistration | Awaitable[AsyncProviderRegistration]]


class ProviderRegistry:
    """Mutable registry of sync provider factories.

    Each provider package (e.g. ``atomicmemory.providers.atomicmemory``)
    calls :meth:`register` on import to add itself to the default
    registry; callers can also create their own registry instances for
    test isolation.
    """

    def __init__(self) -> None:
        self._factories: dict[str, SyncProviderFactory] = {}

    def register(self, name: str, factory: SyncProviderFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Provider '{name}' is already registered")
        self._factories[name] = factory

    def get(self, name: str) -> SyncProviderFactory | None:
        return self._factories.get(name)

    def names(self) -> list[str]:
        return sorted(self._factories.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._factories


class AsyncProviderRegistry:
    """Async counterpart of `ProviderRegistry`."""

    def __init__(self) -> None:
        self._factories: dict[str, AsyncProviderFactory] = {}

    def register(self, name: str, factory: AsyncProviderFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Async provider '{name}' is already registered")
        self._factories[name] = factory

    def get(self, name: str) -> AsyncProviderFactory | None:
        return self._factories.get(name)

    def names(self) -> list[str]:
        return sorted(self._factories.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._factories


default_registry = ProviderRegistry()
default_async_registry = AsyncProviderRegistry()
