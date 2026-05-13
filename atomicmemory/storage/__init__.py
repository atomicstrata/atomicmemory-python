"""Backend artifact-storage API.

This package is the Python peer of `atomicmemory-sdk/src/storage`. It
contains the direct artifact-storage clients and types for
``/v1/storage/artifacts/*``. Local key/value cache adapters live under
``atomicmemory.kv_cache``.
"""

from atomicmemory.storage.async_client import AsyncStorageClient
from atomicmemory.storage.client import StorageClient
from atomicmemory.storage.errors import (
    ArtifactInUseError,
    ArtifactNotFoundError,
    FilecoinDirectStorageNotSupportedError,
    PointerContentNotManagedError,
    StorageClientError,
    UnsupportedCapabilityError,
)
from atomicmemory.storage.types import (
    ArtifactHead,
    ArtifactMetadata,
    ArtifactRange,
    ArtifactRef,
    DeleteArtifactOptions,
    DeleteArtifactPolicy,
    DeleteArtifactResult,
    PutArtifactInput,
    PutManagedInput,
    PutPointerInput,
    StorageArtifactStatus,
    StorageCapabilities,
    StorageClientConfig,
    StoredArtifact,
    VerificationResult,
    VerifyArtifactOptions,
)

__all__ = [
    "ArtifactHead",
    "ArtifactInUseError",
    "ArtifactMetadata",
    "ArtifactNotFoundError",
    "ArtifactRange",
    "ArtifactRef",
    "AsyncStorageClient",
    "DeleteArtifactOptions",
    "DeleteArtifactPolicy",
    "DeleteArtifactResult",
    "FilecoinDirectStorageNotSupportedError",
    "PointerContentNotManagedError",
    "PutArtifactInput",
    "PutManagedInput",
    "PutPointerInput",
    "StorageArtifactStatus",
    "StorageCapabilities",
    "StorageClient",
    "StorageClientConfig",
    "StorageClientError",
    "StoredArtifact",
    "UnsupportedCapabilityError",
    "VerificationResult",
    "VerifyArtifactOptions",
]
