"""Async mirror of test_entities_input_validation.py — asyncio_mode=auto.

All public async methods that accept entity_type must reject non-allowlist
values with EntitiesClientError / error_code == "invalid_entities_input".
Validation fires before any HTTP call — no respx mocking required.
"""

from __future__ import annotations

import pytest

from atomicmemory.entities.async_client import AsyncEntitiesClient
from atomicmemory.entities.errors import EntitiesClientError

_BASE_URL = "https://api.test"
_API_KEY = "test-key"
_BAD_TYPE = "user/../admin"


def _client() -> AsyncEntitiesClient:
    return AsyncEntitiesClient({"apiUrl": _BASE_URL, "apiKey": _API_KEY})


async def test_async_profile_rejects_traversal_entity_type() -> None:
    """profile() raises EntitiesClientError for a traversal entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().profile("bob", entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_get_rejects_traversal_entity_type() -> None:
    """get() raises EntitiesClientError for a traversal entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().get("bob", entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_delete_rejects_traversal_entity_type() -> None:
    """delete() raises EntitiesClientError for a traversal entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().delete("bob", entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_attributes_rejects_traversal_entity_type() -> None:
    """attributes() raises EntitiesClientError for a traversal entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().attributes("bob", entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_memory_history_rejects_traversal_entity_type() -> None:
    """memory_history() raises EntitiesClientError for a traversal entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().memory_history("bob", "mem-1", entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_patch_settings_rejects_traversal_entity_type() -> None:
    """patch_settings() raises EntitiesClientError for a traversal entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().patch_settings("bob", entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_merge_rejects_bad_source_entity_type() -> None:
    """merge() raises EntitiesClientError for a traversal source_entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().merge("bob", "alice", source_entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_merge_rejects_bad_target_entity_type() -> None:
    """merge() raises EntitiesClientError for a traversal target_entity_type."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().merge("bob", "alice", target_entity_type=_BAD_TYPE)  # type: ignore[arg-type]
    assert exc_info.value.error_code == "invalid_entities_input"


async def test_async_profile_valid_entity_type_passes_validation() -> None:
    """profile() with valid entity_type raises network error, not validation error."""
    with pytest.raises(EntitiesClientError) as exc_info:
        await _client().profile("bob", entity_type="agent")
    assert exc_info.value.error_code != "invalid_entities_input"
