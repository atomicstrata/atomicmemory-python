"""Hindsight provider configuration and extension wire models.

Ports the TypeScript SDK's Hindsight provider contract to Python while keeping
Hindsight-specific operation metadata behind named custom extensions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atomicmemory.core.url import validate_api_url
from atomicmemory.memory.types import IngestInput, Scope

HindsightRecallBudget = Literal["low", "mid", "high"]
HindsightTagsMatch = Literal["any", "all", "any_strict", "all_strict"]

HINDSIGHT_DEFAULT_TIMEOUT_SECONDS: float = 30.0
HINDSIGHT_DEFAULT_API_VERSION: str = "v1"
HINDSIGHT_DEFAULT_PROJECT_ID: str = "default"
HINDSIGHT_DEFAULT_MAX_TOKENS: int = 4096
HINDSIGHT_SCOPE_TAGS_MATCH: HindsightTagsMatch = "all_strict"


class HindsightProviderConfig(BaseModel):
    """Inputs to construct a Hindsight provider."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_url: str = Field(alias="apiUrl")
    api_key: str | None = Field(default=None, alias="apiKey")
    timeout_seconds: float = Field(
        default=HINDSIGHT_DEFAULT_TIMEOUT_SECONDS,
        alias="timeoutSeconds",
    )
    api_version: str = Field(default=HINDSIGHT_DEFAULT_API_VERSION, alias="apiVersion")
    project_id: str = Field(default=HINDSIGHT_DEFAULT_PROJECT_ID, alias="projectId")
    default_budget: HindsightRecallBudget | None = Field(default=None, alias="defaultBudget")
    default_max_tokens: int | None = Field(default=None, alias="defaultMaxTokens")
    allow_private_networks: bool = Field(default=True, alias="allowPrivateNetworks")
    """Permit loopback/private/reserved IP literals in ``api_url`` (default True;
    set False to harden). Link-local / cloud-metadata stay blocked regardless."""

    @model_validator(mode="after")
    def _validate_api_url(self) -> HindsightProviderConfig:
        self.api_url = validate_api_url(self.api_url, allow_private_networks=self.allow_private_networks)
        return self


class HindsightRetainResponse(BaseModel):
    """Raw Hindsight retain response exposed through ``hindsight.retain``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    success: bool | None = None
    bank_id: str | None = None
    items_count: int | None = None
    async_: bool | None = Field(default=None, alias="async")
    operation_id: str | None = None
    operation_ids: list[str] | None = None
    usage: dict[str, Any] | None = None


class HindsightOperation(BaseModel):
    """Hindsight background operation status."""

    model_config = ConfigDict(extra="ignore")

    id: str
    task_type: str | None = None
    items_count: int | None = None
    document_id: str | None = None
    created_at: str | None = None
    status: str | None = None
    error_message: str | None = None
    retry_count: int | None = None
    next_retry_at: str | None = None


class HindsightOperationsPage(BaseModel):
    """Page of Hindsight operation statuses."""

    model_config = ConfigDict(extra="ignore")

    bank_id: str | None = None
    operations: list[HindsightOperation] = Field(default_factory=list)


class HindsightRetainHandle:
    """Custom extension handle for raw Hindsight retain calls."""

    def __init__(self, retain_fn: Callable[[IngestInput], HindsightRetainResponse]) -> None:
        self._retain_fn = retain_fn

    def retain(self, input: IngestInput) -> HindsightRetainResponse:
        return self._retain_fn(input)


class HindsightOperationsHandle:
    """Custom extension handle for Hindsight operation status calls."""

    def __init__(
        self,
        list_fn: Callable[[Scope], HindsightOperationsPage],
        get_fn: Callable[[Scope, str], HindsightOperation | None],
    ) -> None:
        self._list_fn = list_fn
        self._get_fn = get_fn

    def list(self, scope: Scope) -> HindsightOperationsPage:
        return self._list_fn(scope)

    def get(self, scope: Scope, operation_id: str) -> HindsightOperation | None:
        return self._get_fn(scope, operation_id)


class AsyncHindsightRetainHandle:
    """Async custom extension handle for raw Hindsight retain calls."""

    def __init__(self, retain_fn: Callable[[IngestInput], Awaitable[HindsightRetainResponse]]) -> None:
        self._retain_fn = retain_fn

    async def retain(self, input: IngestInput) -> HindsightRetainResponse:
        return await self._retain_fn(input)


class AsyncHindsightOperationsHandle:
    """Async custom extension handle for Hindsight operation status calls."""

    def __init__(
        self,
        list_fn: Callable[[Scope], Awaitable[HindsightOperationsPage]],
        get_fn: Callable[[Scope, str], Awaitable[HindsightOperation | None]],
    ) -> None:
        self._list_fn = list_fn
        self._get_fn = get_fn

    async def list(self, scope: Scope) -> HindsightOperationsPage:
        return await self._list_fn(scope)

    async def get(self, scope: Scope, operation_id: str) -> HindsightOperation | None:
        return await self._get_fn(scope, operation_id)
