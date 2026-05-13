"""AtomicMemory provider configuration.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/types.ts:1-36`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

ATOMICMEMORY_DEFAULT_TIMEOUT_SECONDS: float = 30.0
"""Default request timeout (seconds). Mirrors TS ``ATOMICMEMORY_DEFAULT_TIMEOUT`` (ms)."""

ATOMICMEMORY_DEFAULT_API_VERSION: str = "v1"
"""Matches core's mount at `atomicmemory-core/src/app/create-app.ts:31-32`."""


class AtomicMemoryProviderConfig(BaseModel):
    """Inputs to construct an AtomicMemoryProvider."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_url: str = Field(alias="apiUrl")
    """Base URL of the atomicmemory-core instance, e.g. ``http://localhost:3050``."""

    api_key: str | None = Field(default=None, alias="apiKey")
    """Optional bearer token forwarded as ``Authorization: Bearer <api_key>``."""

    timeout_seconds: float = Field(
        default=ATOMICMEMORY_DEFAULT_TIMEOUT_SECONDS,
        alias="timeoutSeconds",
    )
    """Per-request timeout (seconds). Default 30s. Pre-port note: TS uses ms."""

    api_version: str = Field(
        default=ATOMICMEMORY_DEFAULT_API_VERSION,
        alias="apiVersion",
    )
    """API-version segment prepended to every route path (e.g. ``v1`` → ``/v1/...``)."""
