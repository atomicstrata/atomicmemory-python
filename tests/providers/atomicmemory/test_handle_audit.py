"""Tests for AtomicMemoryAudit category."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


@pytest.fixture
def provider() -> AtomicMemoryProvider:
    p = AtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    p.initialize()
    yield p
    p.close()


@respx.mock
def test_summary_decodes_typed_response(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/audit/summary?user_id=u1").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_versions": 10,
                "active_versions": 7,
                "superseded_versions": 3,
                "total_claims": 4,
                "by_mutation_type": {"add": 4, "update": 3},
            },
        )
    )
    summary = provider._handle.audit.summary("u1")  # type: ignore[union-attr]
    assert summary.total_versions == 10
    assert summary.by_mutation_type["add"] == 4


@respx.mock
def test_recent_decodes_mutation_records(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/audit/recent?user_id=u1&limit=5").mock(
        return_value=httpx.Response(
            200,
            json={
                "mutations": [
                    {
                        "id": "v-1",
                        "claim_id": "c-1",
                        "user_id": "u1",
                        "memory_id": "m-1",
                        "content": "hi",
                        "mutation_type": "add",
                        "mutation_reason": None,
                        "actor_model": "gpt-4o",
                        "contradiction_confidence": None,
                        "previous_version_id": None,
                        "superseded_by_version_id": None,
                        "valid_from": "2024-01-01T00:00:00Z",
                        "valid_to": None,
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "count": 1,
            },
        )
    )
    page = provider._handle.audit.recent("u1", limit=5)  # type: ignore[union-attr]
    assert page.count == 1
    assert page.mutations[0].mutation_type == "add"
    assert page.mutations[0].valid_from == datetime(2024, 1, 1, tzinfo=timezone.utc)


@respx.mock
def test_trail_decodes_typed_entries(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/m-1/audit?user_id=u1").mock(
        return_value=httpx.Response(
            200,
            json={
                "memory_id": "m-1",
                "version_count": 2,
                "trail": [
                    {
                        "version_id": "v-1",
                        "claim_id": "c-1",
                        "memory_id": "m-1",
                        "content": "hi",
                        "mutation_type": "add",
                        "mutation_reason": None,
                        "actor_model": None,
                        "contradiction_confidence": None,
                        "previous_version_id": None,
                        "superseded_by_version_id": "v-2",
                        "valid_from": "2024-01-01T00:00:00Z",
                        "valid_to": "2024-02-01T00:00:00Z",
                    }
                ],
            },
        )
    )
    result = provider._handle.audit.trail("m-1", "u1")  # type: ignore[union-attr]
    assert result.memory_id == "m-1"
    assert result.version_count == 2
    assert result.trail[0].superseded_by_version_id == "v-2"
