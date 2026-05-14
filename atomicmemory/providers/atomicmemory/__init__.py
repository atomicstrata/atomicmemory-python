"""AtomicMemory provider — HTTP client for atomicmemory-core.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/`. Importing
this package registers the provider on
`atomicmemory.memory.registry.default_registry` (and the async registry
when both sync and async clients are available).
"""

from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    ProviderRegistration,
    default_async_registry,
    default_registry,
)
from atomicmemory.providers.atomicmemory.async_provider import AsyncAtomicMemoryProvider
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


def _coerce_config(config: object) -> AtomicMemoryProviderConfig:
    if isinstance(config, AtomicMemoryProviderConfig):
        return config
    return AtomicMemoryProviderConfig.model_validate(config)


def _factory(config: object) -> ProviderRegistration:
    """Construct an AtomicMemoryProvider from a config dict or model."""
    return ProviderRegistration(provider=AtomicMemoryProvider(_coerce_config(config)))


def _async_factory(config: object) -> AsyncProviderRegistration:
    return AsyncProviderRegistration(provider=AsyncAtomicMemoryProvider(_coerce_config(config)))


default_registry.register("atomicmemory", _factory)
default_async_registry.register("atomicmemory", _async_factory)


__all__ = [
    "AsyncAtomicMemoryProvider",
    "AtomicMemoryProvider",
    "AtomicMemoryProviderConfig",
]
