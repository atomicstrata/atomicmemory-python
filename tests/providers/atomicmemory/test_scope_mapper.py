"""Tests for the AtomicMemory scope mapper."""

from __future__ import annotations

import pytest

from atomicmemory.core.errors import ValidationError
from atomicmemory.providers.atomicmemory.handle import UserScope, WorkspaceScope
from atomicmemory.providers.atomicmemory.scope_mapper import (
    assert_scope_allows_visibility,
    scope_to_fields,
    scope_to_query_pairs,
    strip_agent_scope,
    strip_read_filters,
)


def test_user_scope_emits_only_user_id() -> None:
    fields = scope_to_fields(UserScope(user_id="u1"))
    assert fields == {"user_id": "u1"}


def test_workspace_scope_emits_full_fields() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1")
    fields = scope_to_fields(scope)
    assert fields == {"user_id": "u1", "workspace_id": "w1", "agent_id": "a1"}


def test_workspace_scope_omits_agent_scope_by_default() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", agent_scope="self")
    fields = scope_to_fields(scope)
    assert "agent_scope" not in fields


def test_workspace_scope_emits_agent_scope_when_opt_in() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", agent_scope="self")
    fields = scope_to_fields(scope, include_agent_scope=True)
    assert fields["agent_scope"] == "self"


def test_user_scope_emits_session_id_when_thread_opted_in() -> None:
    fields = scope_to_fields(UserScope(user_id="u1", thread="thread-1"), include_thread=True)
    assert fields == {"user_id": "u1", "session_id": "thread-1"}


def test_workspace_scope_emits_session_id_when_thread_opted_in() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", thread="thread-1")
    fields = scope_to_fields(scope, include_thread=True)
    assert fields["session_id"] == "thread-1"


def test_query_pairs_repeats_agent_scope_for_lists() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", agent_scope=["a2", "a3"])
    pairs = scope_to_query_pairs(scope, include_agent_scope=True)
    agent_pairs = [v for k, v in pairs if k == "agent_scope"]
    assert agent_pairs == ["a2", "a3"]


def test_query_pairs_emit_session_id_when_thread_opted_in() -> None:
    pairs = scope_to_query_pairs(UserScope(user_id="u1", thread="thread-1"), include_thread=True)
    assert ("session_id", "thread-1") in pairs


def test_visibility_rejected_on_user_scope() -> None:
    with pytest.raises(ValidationError):
        assert_scope_allows_visibility(UserScope(user_id="u1"), "workspace")


def test_visibility_allowed_on_workspace_scope() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1")
    assert_scope_allows_visibility(scope, "workspace")  # no raise


def test_strip_agent_scope_clears_workspace_filter() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", agent_scope="self")
    stripped = strip_agent_scope(scope)
    assert isinstance(stripped, WorkspaceScope)
    assert stripped.agent_scope is None


def test_strip_agent_scope_leaves_user_scope_unchanged() -> None:
    scope = UserScope(user_id="u1")
    assert strip_agent_scope(scope) is scope


def test_strip_agent_scope_preserves_thread() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", thread="thread-1", agent_scope="self")
    stripped = strip_agent_scope(scope)
    assert isinstance(stripped, WorkspaceScope)
    assert stripped.thread == "thread-1"
    assert stripped.agent_scope is None


def test_strip_read_filters_drops_thread_and_agent_scope() -> None:
    scope = WorkspaceScope(user_id="u1", workspace_id="w1", agent_id="a1", thread="thread-1", agent_scope="self")
    stripped = strip_read_filters(scope)
    assert isinstance(stripped, WorkspaceScope)
    assert stripped.thread is None
    assert stripped.agent_scope is None
