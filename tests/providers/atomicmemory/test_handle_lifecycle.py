"""Tests for AtomicMemoryLifecycle category."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.handle import (
    ConsolidationExecutionResult,
    ConsolidationScanResult,
)
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider


@pytest.fixture
def provider() -> AtomicMemoryProvider:
    p = AtomicMemoryProvider(AtomicMemoryProviderConfig(api_url="http://core.test"))
    p.initialize()
    yield p
    p.close()


@respx.mock
def test_consolidate_scan_returns_scan_result(provider: AtomicMemoryProvider) -> None:
    respx.post("http://core.test/v1/memories/consolidate").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories_scanned": 100,
                "clusters_found": 3,
                "memories_in_clusters": 12,
                "clusters": [],
            },
        )
    )
    result = provider._handle.lifecycle.consolidate("u1")  # type: ignore[union-attr]
    assert isinstance(result, ConsolidationScanResult)
    assert result.memories_scanned == 100


@respx.mock
def test_consolidate_execute_returns_execution_result(
    provider: AtomicMemoryProvider,
) -> None:
    route = respx.post("http://core.test/v1/memories/consolidate").mock(
        return_value=httpx.Response(
            200,
            json={
                "clusters_consolidated": 2,
                "memories_archived": 5,
                "memories_created": 1,
                "consolidated_memory_ids": ["m-9"],
            },
        )
    )
    result = provider._handle.lifecycle.consolidate("u1", execute=True)  # type: ignore[union-attr]
    assert isinstance(result, ConsolidationExecutionResult)
    body = json.loads(route.calls[0].request.content)
    assert body["execute"] is True


@respx.mock
def test_decay_dry_run_default_omits_field(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/decay").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories_evaluated": 0,
                "candidates_for_archival": [],
                "retention_threshold": 0.1,
                "avg_retention_score": 0.5,
                "archived": 0,
            },
        )
    )
    provider._handle.lifecycle.decay("u1")  # type: ignore[union-attr]
    body = json.loads(route.calls[0].request.content)
    assert "dry_run" not in body


@respx.mock
def test_decay_explicit_false_emits_field(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/decay").mock(
        return_value=httpx.Response(
            200,
            json={
                "memories_evaluated": 0,
                "candidates_for_archival": [],
                "retention_threshold": 0.1,
                "avg_retention_score": 0.5,
                "archived": 0,
            },
        )
    )
    provider._handle.lifecycle.decay("u1", dry_run=False)  # type: ignore[union-attr]
    body = json.loads(route.calls[0].request.content)
    assert body["dry_run"] is False


@respx.mock
def test_cap_returns_typed_status(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/cap?user_id=u1").mock(
        return_value=httpx.Response(
            200,
            json={
                "active_memories": 50,
                "max_memories": 100,
                "status": "warn",
                "usage_ratio": 0.85,
                "recommendation": "consolidate",
            },
        )
    )
    result = provider._handle.lifecycle.cap("u1")  # type: ignore[union-attr]
    assert result.status == "warn"
    assert result.recommendation == "consolidate"


@respx.mock
def test_reconcile_all_omits_user_id(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/reconcile").mock(
        return_value=httpx.Response(
            200,
            json={
                "processed": 0,
                "resolved": 0,
                "noops": 0,
                "updates": 0,
                "supersedes": 0,
                "deletes": 0,
                "adds": 0,
                "errors": 0,
                "duration_ms": 1,
            },
        )
    )
    provider._handle.lifecycle.reconcile_all()  # type: ignore[union-attr]
    body = json.loads(route.calls[0].request.content)
    assert "user_id" not in body
