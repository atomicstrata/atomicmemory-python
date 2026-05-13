"""Primary clients that expose memory and storage sibling namespaces.

This module mirrors the TypeScript SDK's `AtomicMemoryClient`: callers
configure one core transport boundary and receive both ``memory`` and
``storage`` namespaces backed by the same API URL, API key, and user
scope.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from atomicmemory.client.async_memory_client import AsyncMemoryClient
from atomicmemory.client.memory_client import MemoryClient, MemoryProviderConfigs
from atomicmemory.core.errors import ConfigError
from atomicmemory.core.validation import sanitized_pydantic_errors
from atomicmemory.storage import AsyncStorageClient, StorageClient, StorageClientConfig


class MemoryNamespaceConfig(BaseModel):
    """Configuration for the aggregator's ``memory`` namespace."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    providers: MemoryProviderConfigs
    default_provider: str | None = Field(default=None, alias="defaultProvider")

    @model_validator(mode="after")
    def _require_providers(self) -> MemoryNamespaceConfig:
        if not self.providers:
            raise ValueError("memory.providers must not be empty")
        return self


class AtomicMemoryClientConfig(BaseModel):
    """Configuration for :class:`AtomicMemoryClient` and its async peer."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_url: str = Field(alias="apiUrl")
    api_key: str = Field(alias="apiKey")
    user_id: str = Field(alias="userId")
    timeout_seconds: float = Field(default=30.0, alias="timeoutSeconds")
    memory: MemoryNamespaceConfig | None = None

    @field_validator("api_url")
    @classmethod
    def _validate_api_url(cls, value: str) -> str:
        stripped = value.strip()
        parsed = urlparse(stripped)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("api_url must be an http(s) URL")
        return stripped

    @field_validator("api_key", "user_id")
    @classmethod
    def _validate_non_empty_secret(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value

    @model_validator(mode="after")
    def _require_non_empty(self) -> AtomicMemoryClientConfig:
        if not self.api_url:
            raise ValueError("api_url is required")
        if not self.api_key:
            raise ValueError("api_key is required")
        if not self.user_id:
            raise ValueError("user_id is required")
        return self


class AtomicMemoryClient:
    """Sync primary SDK entry point with ``memory`` and ``storage`` namespaces."""

    def __init__(self, config: AtomicMemoryClientConfig | dict[str, Any]) -> None:
        resolved = _coerce_atomic_config(config)
        memory = _memory_config(resolved)
        self.memory = MemoryClient(memory.providers, memory.default_provider)
        self.storage = StorageClient(_storage_config(resolved))

    def close(self) -> None:
        try:
            self.memory.close()
        finally:
            self.storage.close()

    def __enter__(self) -> AtomicMemoryClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncAtomicMemoryClient:
    """Async primary SDK entry point with ``memory`` and ``storage`` namespaces."""

    def __init__(self, config: AtomicMemoryClientConfig | dict[str, Any]) -> None:
        resolved = _coerce_atomic_config(config)
        memory = _memory_config(resolved)
        self.memory = AsyncMemoryClient(memory.providers, memory.default_provider)
        self.storage = AsyncStorageClient(_storage_config(resolved))

    async def close(self) -> None:
        first_error: BaseException | None = None
        try:
            await self.memory.close()
        except BaseException as exc:
            first_error = exc
        try:
            await self.storage.close()
        except BaseException as exc:
            if first_error is not None:
                raise first_error from exc
            raise
        if first_error is not None:
            raise first_error

    async def __aenter__(self) -> AsyncAtomicMemoryClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


def _coerce_atomic_config(config: AtomicMemoryClientConfig | dict[str, Any]) -> AtomicMemoryClientConfig:
    if isinstance(config, AtomicMemoryClientConfig):
        return config
    try:
        return AtomicMemoryClientConfig.model_validate(config)
    except PydanticValidationError as exc:
        raise ConfigError(
            f"Invalid AtomicMemoryClientConfig: {exc}",
            context={"type": "AtomicMemoryClientConfig", "errors": sanitized_pydantic_errors(exc)},
        ) from exc


def _memory_config(config: AtomicMemoryClientConfig) -> MemoryNamespaceConfig:
    if config.memory is not None:
        return config.memory
    return MemoryNamespaceConfig(
        providers={
            "atomicmemory": {
                "apiUrl": config.api_url,
                "apiKey": config.api_key,
                "timeoutSeconds": config.timeout_seconds,
            }
        }
    )


def _storage_config(config: AtomicMemoryClientConfig) -> StorageClientConfig:
    return StorageClientConfig(
        api_url=config.api_url,
        api_key=config.api_key,
        user_id=config.user_id,
        timeout_seconds=config.timeout_seconds,
    )
