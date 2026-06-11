"""Wire-model tests for the entities namespace.

The /v1/entities wire is snake_case, which matches Python's field names
directly — TS needs ~150 lines of camelCase mappers; Python needs none.
Payloads here are lifted from the TS test fixtures so both SDKs are proven
against identical wire shapes.
"""

from __future__ import annotations

from atomicmemory.entities import (
    DeleteEntityResult,
    EntityDetail,
    EntityListResult,
    EntityProfile,
    EntitySettings,
    MemoryHistory,
    MergeEntitiesResult,
)

# ---------------------------------------------------------------------------
# Fixtures matching the TS __tests__/entities-client.test.ts wire shapes
# ---------------------------------------------------------------------------

_ATTRIBUTE = {
    "entity": "Alice",
    "attribute": "role",
    "value": "PM",
    "type": "string",
    "source_memory_id": None,
    "observed_at": "2026-05-01T00:00:00Z",
}


def test_profile_validates_full_wire_payload() -> None:
    profile = EntityProfile.model_validate(
        {
            "entity_type": "user",
            "entity_id": "alice",
            "profile": {
                "summary": "s",
                "preferences": ["p1"],
                "instructions": [],
                "open_commitments": ["c1"],
            },
            "attributes": [
                {
                    "entity": "alice",
                    "attribute": "role",
                    "value": "admin",
                    "type": "string",
                    "source_memory_id": None,
                    "observed_at": "2026-06-01T00:00:00Z",
                }
            ],
            "memory_count": 3,
            "last_active": None,
            "updated_at": "2026-06-01T00:00:00Z",
        }
    )
    assert profile.profile is not None and profile.profile.open_commitments == ["c1"]
    assert profile.attributes[0].source_memory_id is None


def test_profile_block_may_be_null() -> None:
    profile = EntityProfile.model_validate(
        {
            "entity_type": "user",
            "entity_id": "a",
            "profile": None,
            "attributes": [],
            "memory_count": 0,
            "last_active": None,
            "updated_at": None,
        }
    )
    assert profile.profile is None


def test_entity_list_result_validates() -> None:
    result = EntityListResult.model_validate(
        {
            "entities": [{"entity_type": "user", "entity_id": "alice", "memory_count": 5, "last_active": None}],
            "total": 1,
            "page": 1,
            "page_size": 10,
        }
    )
    assert result.total == 1
    assert result.entities[0].entity_id == "alice"
    assert result.entities[0].last_active is None


def test_entity_detail_validates() -> None:
    result = EntityDetail.model_validate(
        {
            "entity_type": "user",
            "entity_id": "alice",
            "memory_count": 2,
            "attributes": [_ATTRIBUTE],
            "relations": [
                {
                    "target_entity_id": "bob",
                    "relation_type": "colleague",
                    "confidence": 0.9,
                    "valid_to": None,
                }
            ],
            "recent_cards": [
                {
                    "entity_name": "alice",
                    "card_text": "Alice is a PM.",
                    "version": 1,
                    "updated_at": "2026-05-01T00:00:00Z",
                }
            ],
            "updated_at": None,
        }
    )
    assert result.entity_id == "alice"
    assert result.attributes[0].attribute == "role"
    assert result.relations[0].target_entity_id == "bob"
    assert result.recent_cards[0].card_text == "Alice is a PM."


def test_delete_entity_result_validates() -> None:
    result = DeleteEntityResult.model_validate(
        {
            "deleted": {
                "memories": 10,
                "entity_attributes": 5,
                "profile": 1,
                "entities": 1,
                "entity_edges": 3,
                "entity_cards": 2,
            }
        }
    )
    assert result.deleted.memories == 10
    assert result.deleted.entity_attributes == 5
    assert result.deleted.entity_edges == 3
    assert result.deleted.entity_cards == 2


def test_memory_history_validates() -> None:
    result = MemoryHistory.model_validate(
        {
            "memory_id": "mem-1",
            "history": [
                {
                    "version_id": "v1",
                    "event": "created",
                    "content": "Alice is a PM.",
                    "timestamp": "2026-05-01T00:00:00Z",
                    "superseded_by": None,
                },
                {
                    "version_id": "v2",
                    "event": "updated",
                    "content": "Alice is a senior PM.",
                    "timestamp": "2026-05-15T00:00:00Z",
                    "superseded_by": "v2",
                },
            ],
        }
    )
    assert result.memory_id == "mem-1"
    assert len(result.history) == 2
    assert result.history[0].superseded_by is None
    assert result.history[1].superseded_by == "v2"


def test_entity_settings_validates() -> None:
    result = EntitySettings.model_validate(
        {
            "entity_id": "alice",
            "extraction_prompt": "Focus on healthcare.",
            "memory_kinds": None,
            "decay_enabled": True,
            "updated_at": "2026-05-30T00:00:00Z",
        }
    )
    assert result.entity_id == "alice"
    assert result.extraction_prompt == "Focus on healthcare."
    assert result.memory_kinds is None
    assert result.decay_enabled is True


def test_merge_entities_result_validates() -> None:
    result = MergeEntitiesResult.model_validate(
        {
            "merged": {
                "memories_moved": 5,
                "attributes_moved": 3,
                "cards_moved": 2,
            },
            "target_entity_id": "alice",
        }
    )
    assert result.merged.memories_moved == 5
    assert result.merged.attributes_moved == 3
    assert result.target_entity_id == "alice"


def test_entity_detail_defaults_empty_lists() -> None:
    """attributes/relations/recent_cards default to [] when absent from wire."""
    result = EntityDetail.model_validate(
        {
            "entity_type": "user",
            "entity_id": "alice",
            "memory_count": 0,
            "updated_at": None,
        }
    )
    assert result.attributes == []
    assert result.relations == []
    assert result.recent_cards == []


def test_profile_defaults_empty_lists() -> None:
    """preferences/instructions/open_commitments default to [] when absent."""
    result = EntityProfile.model_validate(
        {
            "entity_type": "user",
            "entity_id": "alice",
            "profile": {"summary": "s"},
            "attributes": [],
            "memory_count": 0,
            "last_active": None,
            "updated_at": None,
        }
    )
    assert result.profile is not None
    assert result.profile.preferences == []
    assert result.profile.instructions == []
    assert result.profile.open_commitments == []
