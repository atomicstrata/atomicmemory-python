"""Tests for AtomicMemoryLessons category."""

from __future__ import annotations

import json

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
def test_list_decodes_lessons(provider: AtomicMemoryProvider) -> None:
    respx.get("http://core.test/v1/memories/lessons?user_id=u1").mock(
        return_value=httpx.Response(
            200,
            json={
                "lessons": [
                    {
                        "id": "l-1",
                        "user_id": "u1",
                        "lesson_type": "false_memory",
                        "pattern": "asserts X",
                        "embedding": [0.1, 0.2],
                        "source_memory_ids": ["m-1"],
                        "source_query": "X?",
                        "severity": "high",
                        "active": True,
                        "metadata": {},
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "count": 1,
            },
        )
    )
    page = provider._handle.lessons.list("u1")  # type: ignore[union-attr]
    assert page.count == 1
    assert page.lessons[0].severity == "high"


@respx.mock
def test_report_minimal_body_omits_optional_fields(
    provider: AtomicMemoryProvider,
) -> None:
    route = respx.post("http://core.test/v1/memories/lessons/report").mock(
        return_value=httpx.Response(200, json={"lesson_id": "l-1"})
    )
    provider._handle.lessons.report("u1", "asserts X")  # type: ignore[union-attr]
    body = json.loads(route.calls[0].request.content)
    assert body == {"user_id": "u1", "pattern": "asserts X"}


@respx.mock
def test_report_includes_sources_and_severity(provider: AtomicMemoryProvider) -> None:
    route = respx.post("http://core.test/v1/memories/lessons/report").mock(
        return_value=httpx.Response(200, json={"lesson_id": "l-1"})
    )
    provider._handle.lessons.report(  # type: ignore[union-attr]
        "u1", "asserts X", sources=["m-1", "m-2"], severity="critical"
    )
    body = json.loads(route.calls[0].request.content)
    assert body["source_memory_ids"] == ["m-1", "m-2"]
    assert body["severity"] == "critical"


@respx.mock
def test_delete_uses_delete_method(provider: AtomicMemoryProvider) -> None:
    route = respx.delete("http://core.test/v1/memories/lessons/l-1?user_id=u1").mock(return_value=httpx.Response(204))
    provider._handle.lessons.delete("l-1", "u1")  # type: ignore[union-attr]
    assert route.called
