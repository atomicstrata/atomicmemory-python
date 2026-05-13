"""Mem0 provider — HTTP client for Mem0 OSS or hosted instances.

Port of `atomicmemory-sdk/src/memory/mem0-provider/`. Importing this
package registers `Mem0Provider` on the sync default registry and
`AsyncMem0Provider` on the async registry.
"""

from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    ProviderRegistration,
    default_async_registry,
    default_registry,
)
from atomicmemory.providers.mem0.async_provider import AsyncMem0Provider
from atomicmemory.providers.mem0.config import Mem0ProviderConfig
from atomicmemory.providers.mem0.provider import Mem0Provider


def _coerce_config(config: object) -> Mem0ProviderConfig:
    if isinstance(config, Mem0ProviderConfig):
        return config
    return Mem0ProviderConfig.model_validate(config)


def _factory(config: object) -> ProviderRegistration:
    return ProviderRegistration(provider=Mem0Provider(_coerce_config(config)))


def _async_factory(config: object) -> AsyncProviderRegistration:
    return AsyncProviderRegistration(provider=AsyncMem0Provider(_coerce_config(config)))


default_registry.register("mem0", _factory)
default_async_registry.register("mem0", _async_factory)


__all__ = [
    "AsyncMem0Provider",
    "Mem0Provider",
    "Mem0ProviderConfig",
]
