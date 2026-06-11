"""Entity API client and wire models for /v1/entities.

This package is the Python peer of ``atomicmemory-sdk/src/entities``. It
contains the entity-namespace clients and Pydantic wire models for the
``/v1/entities/*`` endpoints.  The server wire is snake_case throughout,
so Python field names match the wire 1:1 — no mapping layer required.
"""

from atomicmemory.entities.async_client import AsyncEntitiesClient
from atomicmemory.entities.client import EntitiesClient, EntitiesClientConfig
from atomicmemory.entities.errors import EntitiesClientError
from atomicmemory.entities.types import (
    DeletedCounts,
    DeleteEntityResult,
    EntityAttribute,
    EntityCard,
    EntityDetail,
    EntityListResult,
    EntityProfile,
    EntityProfileBlock,
    EntityRelation,
    EntitySettings,
    EntitySummary,
    EntityType,
    MemoryHistory,
    MemoryHistoryEntry,
    MergedCounts,
    MergeEntitiesResult,
)

__all__ = [
    "AsyncEntitiesClient",
    "DeleteEntityResult",
    "DeletedCounts",
    "EntitiesClient",
    "EntitiesClientConfig",
    "EntitiesClientError",
    "EntityAttribute",
    "EntityCard",
    "EntityDetail",
    "EntityListResult",
    "EntityProfile",
    "EntityProfileBlock",
    "EntityRelation",
    "EntitySettings",
    "EntitySummary",
    "EntityType",
    "MemoryHistory",
    "MemoryHistoryEntry",
    "MergeEntitiesResult",
    "MergedCounts",
]
