"""Scope mapper for the AtomicMemory namespace.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/scope-mapper.ts`.
Serializes the AtomicMemory-specific :class:`MemoryScope` discriminated
union to the body/query fields atomicmemory-core expects, with the same
"agent_scope only on POST search routes" policy.
"""

from __future__ import annotations

from typing import Any

from atomicmemory.core.errors import ValidationError
from atomicmemory.providers.atomicmemory.handle import MemoryScope, UserScope, WorkspaceScope


def scope_to_fields(
    scope: MemoryScope,
    *,
    include_agent_scope: bool = False,
    include_thread: bool = False,
) -> dict[str, Any]:
    """Translate a `MemoryScope` to wire-format request fields.

    Args:
        scope: The scope discriminated union.
        include_agent_scope: Emit ``agent_scope`` on the wire. Defaults
            to ``False``; only the search routes opt in (core ignores
            ``agent_scope`` on expand/list/get/delete).
        include_thread: Emit ``session_id`` on routes Core honors:
            ingest, search, and list.

    Returns:
        A dict with ``user_id`` always set, plus ``workspace_id`` /
        ``agent_id`` (and optionally ``agent_scope``) for workspace
        scopes.
    """
    if not isinstance(scope, WorkspaceScope):
        user_fields: dict[str, Any] = {"user_id": scope.user_id}
        if include_thread and scope.thread is not None:
            user_fields["session_id"] = scope.thread
        return user_fields
    workspace_fields: dict[str, Any] = {
        "user_id": scope.user_id,
        "workspace_id": scope.workspace_id,
        "agent_id": scope.agent_id,
    }
    if include_agent_scope and scope.agent_scope is not None:
        workspace_fields["agent_scope"] = scope.agent_scope
    if include_thread and scope.thread is not None:
        workspace_fields["session_id"] = scope.thread
    return workspace_fields


def scope_to_query_pairs(
    scope: MemoryScope,
    *,
    include_agent_scope: bool = False,
    include_thread: bool = False,
) -> list[tuple[str, str]]:
    """Translate a scope to ``[(key, value)]`` pairs for query strings.

    httpx's ``params=`` accepts a list of pairs, which lets us repeat a
    key (``agent_scope``) for list values without joining with commas.
    Defaults to **not** sending ``agent_scope`` — only POST search
    routes honor it, and they use bodies, not query strings.
    """
    pairs: list[tuple[str, str]] = [("user_id", scope.user_id)]
    if isinstance(scope, WorkspaceScope):
        pairs.append(("workspace_id", scope.workspace_id))
        pairs.append(("agent_id", scope.agent_id))
        if include_agent_scope and scope.agent_scope is not None:
            value = scope.agent_scope
            if isinstance(value, list):
                pairs.extend(("agent_scope", v) for v in value)
            else:
                pairs.append(("agent_scope", value))
    if include_thread and scope.thread is not None:
        pairs.append(("session_id", scope.thread))
    return pairs


def assert_scope_allows_visibility(scope: MemoryScope, visibility: str | None) -> None:
    """Raise if a user-scope ingest tries to set workspace-only `visibility`.

    Visibility is a workspace-only write-time label. Sending it on
    user-scope ingest is silently dropped by core; the SDK fails closed.
    """
    if visibility is not None and not isinstance(scope, WorkspaceScope):
        raise ValidationError(
            "ingest `visibility` is only valid with workspace scope; omit it or use a workspace scope variant.",
            context={"scope_kind": scope.kind, "visibility": visibility},
        )


def strip_agent_scope(scope: MemoryScope) -> MemoryScope:
    """Drop ``agent_scope`` from a workspace scope before echoing it back.

    Used on routes that don't honor ``agent_scope`` (expand/list/get/
    delete) so returned memories don't lie about the filter that wasn't
    applied.
    """
    if not isinstance(scope, WorkspaceScope):
        return scope
    return WorkspaceScope(
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        agent_id=scope.agent_id,
        thread=scope.thread,
    )


def strip_read_filters(scope: MemoryScope) -> MemoryScope:
    """Drop filters the target route did not apply before echoing scope."""
    if not isinstance(scope, WorkspaceScope):
        return UserScope(user_id=scope.user_id)
    return WorkspaceScope(
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        agent_id=scope.agent_id,
    )
