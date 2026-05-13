"""Public client facades for memory and storage namespaces."""

from atomicmemory.client.async_memory_client import AsyncMemoryClient, AsyncProviderStatus
from atomicmemory.client.atomic_memory_client import (
    AsyncAtomicMemoryClient,
    AtomicMemoryClient,
    AtomicMemoryClientConfig,
    MemoryNamespaceConfig,
)
from atomicmemory.client.memory_client import MemoryClient, MemoryProviderConfigs, ProviderStatus

__all__ = [
    "AsyncAtomicMemoryClient",
    "AsyncMemoryClient",
    "AsyncProviderStatus",
    "AtomicMemoryClient",
    "AtomicMemoryClientConfig",
    "MemoryClient",
    "MemoryNamespaceConfig",
    "MemoryProviderConfigs",
    "ProviderStatus",
]
