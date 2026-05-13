"""Smoke test: package imports and version is set."""

from __future__ import annotations


def test_top_level_imports() -> None:
    import atomicmemory

    assert atomicmemory.__version__ == "1.0.0"
    assert atomicmemory.Scope is not None
    assert atomicmemory.Memory is not None
    assert atomicmemory.AtomicMemoryError is not None
    assert atomicmemory.ArtifactRange(start=0, end=1).start == 0


def test_subpackage_imports() -> None:
    from atomicmemory.core import EventEmitter, RetryConfig, get_logger
    from atomicmemory.memory.provider import BaseAsyncMemoryProvider, BaseMemoryProvider
    from atomicmemory.memory.registry import (
        AsyncProviderRegistry,
        ProviderRegistry,
        default_async_registry,
        default_registry,
    )
    from atomicmemory.memory.service import (
        AsyncMemoryService,
        MemoryService,
        MemoryServiceConfig,
    )

    assert EventEmitter is not None
    assert RetryConfig is not None
    assert get_logger() is not None
    assert BaseMemoryProvider is not None
    assert BaseAsyncMemoryProvider is not None
    assert isinstance(default_registry, ProviderRegistry)
    assert isinstance(default_async_registry, AsyncProviderRegistry)
    assert MemoryService is not None
    assert AsyncMemoryService is not None
    assert MemoryServiceConfig is not None
