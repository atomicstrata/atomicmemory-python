"""Framework-neutral ingest/search tools with an application-owned user scope."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypedDict, TypeVar

from pydantic import BaseModel

from atomicmemory.client.async_memory_client import AsyncMemoryClient
from atomicmemory.client.memory_client import MemoryClient
from atomicmemory.core.errors import AtomicMemoryError, ConfigError
from atomicmemory.memory.types import IngestResult, Scope, SearchRequest, TextIngest
from atomicmemory.tools_models import IngestArguments, MemorySearchOutput, SearchArguments, ToolScope, project_search

_Result = TypeVar("_Result", bound=BaseModel)
_Arguments = TypeVar("_Arguments", bound=BaseModel)


class MemoryToolError(AtomicMemoryError):
    """Safe model-facing failure. A failed write may still have persisted."""


@dataclass(frozen=True)
class MemoryTool(Generic[_Result]):
    """Sync tool descriptor. Pass decoded JSON arguments to ``execute``.

    Attributes:
        name: Stable tool name for framework registration.
        description: Model-facing purpose.
        parameters: JSON Schema for model arguments; identity is excluded.
        execute: Validates arguments and calls the initialized client.
    """

    name: str
    description: str
    parameters: dict[str, object]
    execute: Callable[[dict[str, object]], _Result]


@dataclass(frozen=True)
class AsyncMemoryTool(Generic[_Result]):
    """Async tool descriptor with the same schemas and outputs as ``MemoryTool``."""

    name: str
    description: str
    parameters: dict[str, object]
    execute: Callable[[dict[str, object]], Awaitable[_Result]]


class MemoryTools(TypedDict):
    """Both sync tools, with operation-specific result types."""

    memory_ingest: MemoryTool[IngestResult]
    memory_search: MemoryTool[MemorySearchOutput]


class AsyncMemoryTools(TypedDict):
    """Both async tools, with operation-specific result types."""

    memory_ingest: AsyncMemoryTool[IngestResult]
    memory_search: AsyncMemoryTool[MemorySearchOutput]


def _execute(schema: type[_Arguments], arguments: dict[str, object], run: Callable[[_Arguments], _Result]) -> _Result:
    try:
        return run(schema.model_validate(arguments))
    except Exception:
        raise MemoryToolError("Memory tool failed.") from None


async def _execute_async(
    schema: type[_Arguments], arguments: dict[str, object], run: Callable[[_Arguments], Awaitable[_Result]]
) -> _Result:
    try:
        return await run(schema.model_validate(arguments))
    except Exception:
        raise MemoryToolError("Memory tool failed.") from None


def _user_scope(user: str) -> str:
    try:
        return ToolScope(user=user).user
    except Exception:
        raise ConfigError("Memory tools require a valid application-owned user.") from None


def memory_tools(*, client: MemoryClient, user: str) -> MemoryTools:
    """Return two sync tools for one fixed user. Initialize the client first.

    Args:
        client: Application-owned initialized memory client.
        user: Authenticated application user; never supplied by the model.

    Returns:
        ``memory_ingest`` and ``memory_search`` descriptors. Serialize results
        with ``model_dump(mode="json", exclude_none=True)`` for your framework.

    Raises:
        ConfigError: The user is blank, too long, or a project identifier.
    """
    bound_user = _user_scope(user)

    def ingest(parsed: IngestArguments) -> IngestResult:
        return client.ingest(TextIngest(content=parsed.content, scope=Scope(user=bound_user)))

    def search(parsed: SearchArguments) -> MemorySearchOutput:
        page = client.search(SearchRequest(query=parsed.query, limit=parsed.limit, scope=Scope(user=bound_user)))
        return project_search(page, parsed.limit)

    return {
        "memory_ingest": MemoryTool(
            "memory_ingest",
            "Store a fact in memory. Ingest IDs are backend reports, not correction guarantees.",
            IngestArguments.model_json_schema(),
            lambda args: _execute(IngestArguments, args, ingest),
        ),
        "memory_search": MemoryTool(
            "memory_search",
            "Search saved facts for the current user. Scores are provider-specific.",
            SearchArguments.model_json_schema(),
            lambda args: _execute(SearchArguments, args, search),
        ),
    }


def async_memory_tools(*, client: AsyncMemoryClient, user: str) -> AsyncMemoryTools:
    """Return async tools for one fixed user after ``await client.initialize()``.

    Args:
        client: Application-owned initialized async memory client.
        user: Authenticated application user; never supplied by the model.

    Returns:
        The same descriptors as ``memory_tools``, with awaitable execution.
        Cancellation propagates without an automatic retry or rollback claim.

    Raises:
        ConfigError: The user is blank, too long, or a project identifier.
    """
    bound_user = _user_scope(user)

    async def ingest(parsed: IngestArguments) -> IngestResult:
        return await client.ingest(TextIngest(content=parsed.content, scope=Scope(user=bound_user)))

    async def search(parsed: SearchArguments) -> MemorySearchOutput:
        page = await client.search(SearchRequest(query=parsed.query, limit=parsed.limit, scope=Scope(user=bound_user)))
        return project_search(page, parsed.limit)

    return {
        "memory_ingest": AsyncMemoryTool(
            "memory_ingest",
            "Store a fact in memory. Ingest IDs are backend reports, not correction guarantees.",
            IngestArguments.model_json_schema(),
            lambda args: _execute_async(IngestArguments, args, ingest),
        ),
        "memory_search": AsyncMemoryTool(
            "memory_search",
            "Search saved facts for the current user. Scores are provider-specific.",
            SearchArguments.model_json_schema(),
            lambda args: _execute_async(SearchArguments, args, search),
        ),
    }
