"""Wire models for the /v1/entities API.

Port of ``atomicmemory-sdk/src/entities/types.ts``.  The server wire uses
snake_case throughout, so Python field names match the wire 1:1 —
the entire camelCase mapping layer present in the TS SDK (~150 lines) is
absent here: ``model_validate`` handles everything directly.

All timestamp fields are ``str`` (house wire-client style; TS ``string``).
``extra="ignore"`` on result models mirrors the memory-models precedent
(``memory/types.py``: Memory/IngestResult/SearchResult) — entities validates
raw wire payloads like the TS mappers, which silently drop unknown keys.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["user", "agent", "session"]


class EntityAttribute(BaseModel):
    """A single attribute triple for an entity."""

    model_config = ConfigDict(extra="ignore")

    entity: str
    attribute: str
    value: str
    type: str
    source_memory_id: str | None
    observed_at: str


class EntityRelation(BaseModel):
    """A directed relation from one entity to another."""

    model_config = ConfigDict(extra="ignore")

    target_entity_id: str
    relation_type: str
    confidence: float
    valid_to: str | None


class EntityCard(BaseModel):
    """A versioned narrative card about an entity."""

    model_config = ConfigDict(extra="ignore")

    entity_name: str
    card_text: str
    version: int
    updated_at: str


class EntityProfileBlock(BaseModel):
    """The distilled profile for an entity."""

    model_config = ConfigDict(extra="ignore")

    summary: str
    preferences: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    open_commitments: list[str] = Field(default_factory=list)


class EntityProfile(BaseModel):
    """Full entity profile returned by GET /v1/entities/{type}/{id}/profile."""

    model_config = ConfigDict(extra="ignore")

    entity_type: EntityType
    entity_id: str
    profile: EntityProfileBlock | None
    attributes: list[EntityAttribute] = Field(default_factory=list)
    memory_count: int
    last_active: str | None
    updated_at: str | None


class EntitySummary(BaseModel):
    """Lightweight entity summary used in list results."""

    model_config = ConfigDict(extra="ignore")

    entity_type: EntityType
    entity_id: str
    memory_count: int
    last_active: str | None


class EntityListResult(BaseModel):
    """Paginated entity list returned by GET /v1/entities."""

    model_config = ConfigDict(extra="ignore")

    entities: list[EntitySummary] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class EntityDetail(BaseModel):
    """Full entity detail returned by GET /v1/entities/{type}/{id}."""

    model_config = ConfigDict(extra="ignore")

    entity_type: EntityType
    entity_id: str
    memory_count: int
    attributes: list[EntityAttribute] = Field(default_factory=list)
    relations: list[EntityRelation] = Field(default_factory=list)
    recent_cards: list[EntityCard] = Field(default_factory=list)
    updated_at: str | None


class DeletedCounts(BaseModel):
    """Row counts from a cascade entity delete."""

    model_config = ConfigDict(extra="ignore")

    memories: int
    entity_attributes: int
    profile: int
    entities: int
    entity_edges: int
    entity_cards: int


class DeleteEntityResult(BaseModel):
    """Result returned by DELETE /v1/entities/{type}/{id}."""

    model_config = ConfigDict(extra="ignore")

    deleted: DeletedCounts


class MemoryHistoryEntry(BaseModel):
    """One version entry in a memory's edit history."""

    model_config = ConfigDict(extra="ignore")

    version_id: str
    event: str
    content: str
    timestamp: str
    superseded_by: str | None


class MemoryHistory(BaseModel):
    """Full edit history for a single memory."""

    model_config = ConfigDict(extra="ignore")

    memory_id: str
    history: list[MemoryHistoryEntry] = Field(default_factory=list)


class EntitySettings(BaseModel):
    """Per-entity extraction settings returned by PATCH /v1/entities/{type}/{id}/settings."""

    model_config = ConfigDict(extra="ignore")

    entity_id: str
    extraction_prompt: str | None
    memory_kinds: list[str] | None
    decay_enabled: bool
    updated_at: str


class MergedCounts(BaseModel):
    """Row counts from an entity merge operation."""

    model_config = ConfigDict(extra="ignore")

    memories_moved: int
    attributes_moved: int
    cards_moved: int


class MergeEntitiesResult(BaseModel):
    """Result returned by POST /v1/entities/merge."""

    model_config = ConfigDict(extra="ignore")

    merged: MergedCounts
    target_entity_id: str
