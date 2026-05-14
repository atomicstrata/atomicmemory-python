"""Hindsight provider — HTTP client for Hindsight Cloud or self-hosted APIs."""

from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    ProviderRegistration,
    default_async_registry,
    default_registry,
)
from atomicmemory.providers.hindsight.async_provider import AsyncHindsightProvider
from atomicmemory.providers.hindsight.config import (
    AsyncHindsightOperationsHandle,
    AsyncHindsightRetainHandle,
    HindsightOperation,
    HindsightOperationsHandle,
    HindsightOperationsPage,
    HindsightProviderConfig,
    HindsightRetainHandle,
    HindsightRetainResponse,
)
from atomicmemory.providers.hindsight.provider import HindsightProvider


def _coerce_config(config: object) -> HindsightProviderConfig:
    if isinstance(config, HindsightProviderConfig):
        return config
    return HindsightProviderConfig.model_validate(config)


def _factory(config: object) -> ProviderRegistration:
    return ProviderRegistration(provider=HindsightProvider(_coerce_config(config)))


def _async_factory(config: object) -> AsyncProviderRegistration:
    return AsyncProviderRegistration(provider=AsyncHindsightProvider(_coerce_config(config)))


default_registry.register("hindsight", _factory)
default_async_registry.register("hindsight", _async_factory)


__all__ = [
    "AsyncHindsightOperationsHandle",
    "AsyncHindsightProvider",
    "AsyncHindsightRetainHandle",
    "HindsightOperation",
    "HindsightOperationsHandle",
    "HindsightOperationsPage",
    "HindsightProvider",
    "HindsightProviderConfig",
    "HindsightRetainHandle",
    "HindsightRetainResponse",
]
