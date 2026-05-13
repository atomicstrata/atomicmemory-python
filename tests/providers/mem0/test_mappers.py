"""Tests for Mem0 wire-format mappers + body builders."""

from __future__ import annotations

from atomicmemory.memory.types import Message, MessageIngest, Scope, TextIngest
from atomicmemory.providers.mem0.config import Mem0ProviderConfig
from atomicmemory.providers.mem0.mappers import (
    build_ingest_body,
    build_search_body,
    resolve_infer_flag,
    to_ingest_result,
    to_memory,
    unwrap_mem0_array,
)

_CFG = Mem0ProviderConfig(api_url="http://mem0.test")


def test_unwrap_array_handles_bare_list() -> None:
    assert unwrap_mem0_array([{"id": "1"}, {"id": "2"}]) == [{"id": "1"}, {"id": "2"}]


def test_unwrap_array_handles_results_envelope() -> None:
    assert unwrap_mem0_array({"results": [{"id": "1"}]}) == [{"id": "1"}]


def test_unwrap_array_returns_empty_for_unknown_shape() -> None:
    assert unwrap_mem0_array({"foo": "bar"}) == []


def test_to_memory_extracts_nested_data_memory() -> None:
    raw = {"id": "m-1", "data": {"memory": "nested text"}, "created_at": "2024-01-01T00:00:00Z"}
    memory = to_memory(raw, Scope(user="u1"))
    assert memory.content == "nested text"


def test_to_memory_prefers_flat_memory_over_nested() -> None:
    raw = {"id": "m-1", "memory": "flat", "data": {"memory": "nested"}}
    memory = to_memory(raw, Scope(user="u1"))
    assert memory.content == "flat"


def test_to_ingest_result_partitions_by_event() -> None:
    raws = [
        {"id": "1", "event": "ADD"},
        {"id": "2", "event": "UPDATE"},
        {"id": "3", "event": "NONE"},
        {"id": "4", "event": "weird"},
    ]
    result = to_ingest_result(raws)
    assert result.created == ["1", "4"]
    assert result.updated == ["2"]
    assert result.unchanged == ["3"]


def test_resolve_infer_metadata_overrides_config_default() -> None:
    cfg = Mem0ProviderConfig(api_url="http://x", default_infer=True)
    ingest = TextIngest(content="hi", scope=Scope(user="u1"), metadata={"infer": False})
    assert resolve_infer_flag(ingest, cfg) is False


def test_build_ingest_body_text_mode_wraps_messages() -> None:
    body = build_ingest_body(TextIngest(content="hi", scope=Scope(user="u1")), "u1", _CFG)
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["user_id"] == "u1"
    assert body["infer"] is True


def test_build_ingest_body_strips_infer_from_metadata() -> None:
    body = build_ingest_body(
        TextIngest(content="hi", scope=Scope(user="u1"), metadata={"infer": False, "k": "v"}),
        "u1",
        _CFG,
    )
    assert body["metadata"] == {"k": "v"}
    assert body["infer"] is False


def test_build_ingest_body_messages_mode_passes_through() -> None:
    body = build_ingest_body(
        MessageIngest(messages=[Message(role="user", content="hi")], scope=Scope(user="u1")),
        "u1",
        _CFG,
    )
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_build_search_body_nests_filters_and_attaches_enterprise() -> None:
    cfg = Mem0ProviderConfig(api_url="http://x", org_id="o1", project_id="p1")
    body = build_search_body("q", Scope(user="u1", agent="a1", thread="t1"), cfg, limit=5)
    assert body["filters"] == {"user_id": "u1", "agent_id": "a1", "run_id": "t1"}
    assert body["limit"] == 5
    assert body["org_id"] == "o1"
    assert body["project_id"] == "p1"


def test_build_ingest_body_attaches_enterprise_and_scope_ids() -> None:
    cfg = Mem0ProviderConfig(api_url="http://x", org_id="o1", project_id="p1")
    body = build_ingest_body(TextIngest(content="hi", scope=Scope(user="u1", agent="a1", thread="t1")), "u1", cfg)
    assert body["agent_id"] == "a1"
    assert body["run_id"] == "t1"
    assert body["org_id"] == "o1"
    assert body["project_id"] == "p1"
