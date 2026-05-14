"""Tests for Hindsight request builders and response mappers."""

from __future__ import annotations

import pytest

from atomicmemory.memory.types import Message, MessageIngest, Scope, TextIngest
from atomicmemory.providers.hindsight.config import HindsightProviderConfig
from atomicmemory.providers.hindsight.mappers import (
    build_recall_request,
    build_reflect_request,
    build_retain_request,
    to_memory,
    to_search_result,
    unwrap_results,
)


def test_build_retain_request_maps_scope_tags_and_metadata() -> None:
    body = build_retain_request(
        TextIngest(
            content="Alice likes aisle seats.",
            scope=Scope(user="u1", agent="sdk", namespace="travel", thread="t1"),
            metadata={"kind": "preference"},
        )
    )

    item = body["items"][0]
    assert body["async"] is False
    assert item["content"] == "Alice likes aisle seats."
    assert item["metadata"] == {"kind": "preference"}
    assert item["tags"] == ["agent:sdk", "namespace:travel", "thread:t1"]


def test_build_retain_request_converts_messages_to_transcript() -> None:
    body = build_retain_request(
        MessageIngest(
            messages=[
                Message(role="user", content="hi"),
                Message(role="assistant", content="hello"),
            ],
            scope=Scope(user="u1"),
        )
    )

    assert body["items"][0]["content"] == "user: hi\nassistant: hello"


def test_build_recall_request_uses_max_tokens_and_all_strict_tags() -> None:
    body = build_recall_request(
        "q",
        Scope(user="u1", agent="sdk"),
        HindsightProviderConfig(api_url="http://hindsight.test", default_budget="mid"),
    )

    assert body["max_tokens"] == 4096
    assert body["budget"] == "mid"
    assert body["tags"] == ["agent:sdk"]
    assert body["tags_match"] == "all_strict"


def test_build_recall_request_preserves_explicit_zero_max_tokens() -> None:
    body = build_recall_request(
        "q",
        Scope(user="u1"),
        HindsightProviderConfig(api_url="http://hindsight.test", default_max_tokens=128),
        max_tokens=0,
    )

    assert body["max_tokens"] == 0


def test_build_reflect_request_uses_same_scope_tags() -> None:
    body = build_reflect_request("q", Scope(user="u1", agent="sdk"))
    assert body == {"query": "q", "tags": ["agent:sdk"], "tags_match": "all_strict"}


def test_unwrap_results_rejects_unknown_shapes() -> None:
    with pytest.raises(ValueError, match="results array"):
        unwrap_results({"items": []})


def test_to_memory_maps_documented_fields_strictly() -> None:
    memory = to_memory(
        {
            "id": "m-1",
            "text": "Alice likes aisles.",
            "type": "world",
            "created_at": "2024-01-01T00:00:00Z",
            "tags": ["agent:sdk"],
        },
        Scope(user="u1"),
    )

    assert memory.content == "Alice likes aisles."
    assert memory.kind == "fact"
    assert memory.metadata == {"hindsightType": "world", "tags": ["agent:sdk"]}


def test_to_search_result_uses_zero_score_sentinel() -> None:
    result = to_search_result(
        {
            "id": "m-1",
            "text": "Alice likes aisles.",
            "created_at": "2024-01-01T00:00:00Z",
        },
        Scope(user="u1"),
    )

    assert result.score == 0.0


def test_to_memory_requires_timestamp() -> None:
    with pytest.raises(ValueError, match="missing timestamp"):
        to_memory({"id": "m-1", "text": "no date"}, Scope(user="u1"))
