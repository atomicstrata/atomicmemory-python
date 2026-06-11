"""MemoryClient — sync facade for the V3 memory layer.

Port of `atomicmemory-sdk/src/client/memory-client.ts`. Wraps a
:class:`atomicmemory.memory.service.MemoryService` and the configured
providers, providing the public API users construct in application
code. Async users get the same surface via
``atomicmemory.AsyncMemoryClient``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

# Importing the provider packages registers their factories.
import atomicmemory.providers.atomicmemory
import atomicmemory.providers.hindsight
import atomicmemory.providers.mem0  # noqa: F401
from atomicmemory.core.errors import ConfigError, NotInitializedError, ValidationError
from atomicmemory.core.validation import sanitized_pydantic_errors
from atomicmemory.memory.provider import BaseMemoryProvider
from atomicmemory.memory.registry import ProviderRegistry, default_registry
from atomicmemory.memory.service import MemoryService, MemoryServiceConfig
from atomicmemory.memory.types import (
    Capabilities,
    ContextPackage,
    IngestInput,
    IngestResult,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    PackageRequest,
    SearchRequest,
    SearchResultPage,
)
from atomicmemory.providers.atomicmemory.handle_impl import AtomicMemoryHandle

# IngestInput is a discriminated union; TypeAdapter is the only way to
# validate from a plain dict since BaseModel.model_validate would not
# know which variant to pick.
_INGEST_ADAPTER: TypeAdapter[IngestInput] = TypeAdapter(IngestInput)


def _wrap_pydantic_error(type_name: str, exc: PydanticValidationError) -> ValidationError:
    """Translate a Pydantic ValidationError into the SDK's ValidationError.

    The SDK contract is that every SDK-raised exception inherits from
    `AtomicMemoryError`. Without this wrapping, callers passing an
    invalid dict at the client boundary would see Pydantic's exception
    leak directly out of `MemoryClient`.
    """
    return ValidationError(
        f"Invalid {type_name}: {exc}",
        context={"type": type_name, "errors": sanitized_pydantic_errors(exc)},
    )


def _coerce_ingest(value: IngestInput | dict[str, Any]) -> IngestInput:
    if isinstance(value, dict):
        try:
            return _INGEST_ADAPTER.validate_python(value)
        except PydanticValidationError as exc:
            raise _wrap_pydantic_error("IngestInput", exc) from exc
    return value


def _coerce_search(value: SearchRequest | dict[str, Any]) -> SearchRequest:
    if isinstance(value, dict):
        try:
            return SearchRequest.model_validate(value)
        except PydanticValidationError as exc:
            raise _wrap_pydantic_error("SearchRequest", exc) from exc
    return value


def _coerce_package(value: PackageRequest | dict[str, Any]) -> PackageRequest:
    if isinstance(value, dict):
        try:
            return PackageRequest.model_validate(value)
        except PydanticValidationError as exc:
            raise _wrap_pydantic_error("PackageRequest", exc) from exc
    return value


def _coerce_ref(value: MemoryRef | dict[str, Any]) -> MemoryRef:
    if isinstance(value, dict):
        try:
            return MemoryRef.model_validate(value)
        except PydanticValidationError as exc:
            raise _wrap_pydantic_error("MemoryRef", exc) from exc
    return value


def _coerce_list_request(value: ListRequest | dict[str, Any]) -> ListRequest:
    if isinstance(value, dict):
        try:
            return ListRequest.model_validate(value)
        except PydanticValidationError as exc:
            raise _wrap_pydantic_error("ListRequest", exc) from exc
    return value


MemoryProviderConfigs = dict[str, Any]
"""Map of provider name → provider config (model or dict)."""


@dataclass
class ProviderStatus:
    """Summary of one configured provider's runtime state."""

    name: str
    initialized: bool
    capabilities: Capabilities | None


# Module-level alias so `MemoryClient.list` (the method) does not shadow
# the builtin `list` in return-type annotations within the class body.
_ProviderStatusList = list[ProviderStatus]


class MemoryClient:
    """Sync entry point for the V3 memory API.

    Example:
        >>> with MemoryClient(providers={"atomicmemory": {"api_url": "http://localhost:17350"}}) as memory:
        ...     memory.initialize()
        ...     memory.ingest({"mode": "text", "content": "hi", "scope": {"user": "u1"}})
    """

    def __init__(
        self,
        providers: MemoryProviderConfigs,
        default_provider: str | None = None,
    ) -> None:
        if not providers:
            raise ConfigError(
                'MemoryClient requires at least one provider config. Pass e.g. {"atomicmemory": {"api_url": "..."}}.'
            )
        chosen_default = default_provider or _pick_first_provider_key(providers)
        if chosen_default is None:
            raise ConfigError("No usable provider config supplied")
        self._service = MemoryService(
            MemoryServiceConfig(
                default_provider=chosen_default,
                provider_configs=dict(providers),
            )
        )
        self._initialized = False
        self._init_lock = threading.Lock()
        self._init_error: Exception | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, registry: ProviderRegistry | None = None) -> None:
        """Initialize all configured providers. Idempotent and thread-safe.

        Concurrent and subsequent calls share a single initialization run
        (the first call's ``registry`` wins; later arguments are ignored).
        A FAILED initialization is sticky: retrying re-raises the original
        error — resolve the cause and construct a new client. A successful
        lifecycle stays re-openable: ``close()`` returns the client to the
        uninitialized state. Factories must not call back into this client
        instance; the non-reentrant lock would deadlock.
        """
        with self._init_lock:
            if self._initialized:
                return
            if self._init_error is not None:
                raise self._init_error
            try:
                self._service.initialize(registry if registry is not None else default_registry)
            except Exception as exc:
                # Sticky failures are real initialization errors ONLY —
                # KeyboardInterrupt/SystemExit propagate without poisoning the client.
                self._init_error = exc
                raise
            self._initialized = True

    def close(self) -> None:
        """Close every initialized provider; safe to call multiple times.

        A pending sync initialize holds the lock, so close() blocks until
        initialization finishes, including any network I/O it performs —
        deterministic by construction. A client that never initialized
        successfully is unaffected: close() is a no-op and the sticky
        initialization error is preserved — construct a new client.
        """
        with self._init_lock:
            if not self._initialized:
                return
            try:
                self._service.close()
            finally:
                self._initialized = False

    def __enter__(self) -> MemoryClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Core operations (each pair: gated + direct mirror to TS surface)
    # ------------------------------------------------------------------

    def ingest(self, input: IngestInput | dict[str, Any]) -> IngestResult:
        self._assert_initialized()
        return self._service.ingest(_coerce_ingest(input))

    def ingest_direct(self, input: IngestInput | dict[str, Any]) -> IngestResult:
        """Identical to :meth:`ingest`; preserved for wrapper-subclass parity with TS."""
        self._assert_initialized()
        return self._service.ingest(_coerce_ingest(input))

    def search(self, request: SearchRequest | dict[str, Any]) -> SearchResultPage:
        self._assert_initialized()
        return self._service.search(_coerce_search(request))

    def search_direct(self, request: SearchRequest | dict[str, Any]) -> SearchResultPage:
        """Identical to :meth:`search`; preserved for wrapper-subclass parity with TS."""
        self._assert_initialized()
        return self._service.search(_coerce_search(request))

    def package(self, request: PackageRequest | dict[str, Any]) -> ContextPackage:
        self._assert_initialized()
        return self._service.package(_coerce_package(request))

    def package_direct(self, request: PackageRequest | dict[str, Any]) -> ContextPackage:
        """Identical to :meth:`package`; preserved for wrapper-subclass parity with TS."""
        self._assert_initialized()
        return self._service.package(_coerce_package(request))

    def get(self, ref: MemoryRef | dict[str, Any]) -> Memory | None:
        self._assert_initialized()
        return self._service.get(_coerce_ref(ref))

    def delete(self, ref: MemoryRef | dict[str, Any]) -> None:
        self._assert_initialized()
        self._service.delete(_coerce_ref(ref))

    def list(self, request: ListRequest | dict[str, Any]) -> ListResultPage:
        self._assert_initialized()
        return self._service.list(_coerce_list_request(request))

    # ------------------------------------------------------------------
    # Capability + provider inspection
    # ------------------------------------------------------------------

    def capabilities(self, provider_name: str | None = None) -> Capabilities:
        self._assert_initialized()
        return self._service.get_provider(provider_name).capabilities()

    def get_extension(self, extension_name: str, provider_name: str | None = None) -> Any | None:
        self._assert_initialized()
        provider = self._service.get_provider(provider_name)
        return provider.get_extension(extension_name)

    def get_provider_status(self) -> _ProviderStatusList:
        configured = self._service.get_configured_providers()
        if not self._initialized:
            return [ProviderStatus(name=n, initialized=False, capabilities=None) for n in configured]
        available = set(self._service.get_available_providers())
        statuses: _ProviderStatusList = []
        for n in configured:
            if n not in available:
                statuses.append(ProviderStatus(name=n, initialized=False, capabilities=None))
                continue
            statuses.append(
                ProviderStatus(
                    name=n,
                    initialized=True,
                    capabilities=self._service.get_provider(n).capabilities(),
                )
            )
        return statuses

    def get_provider(self, name: str | None = None) -> BaseMemoryProvider:
        self._assert_initialized()
        return self._service.get_provider(name)

    @property
    def atomicmemory(self) -> AtomicMemoryHandle | None:
        """Typed access to AtomicMemory-specific routes.

        Returns ``None`` when the client is not yet initialized or the
        ``atomicmemory`` provider was not configured.
        """
        if not self._initialized:
            return None
        if "atomicmemory" not in self._service.get_configured_providers():
            return None
        provider = self._service.get_provider("atomicmemory")
        handle = provider.get_extension("atomicmemory.base")
        if not isinstance(handle, AtomicMemoryHandle):
            return None
        return handle

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _assert_initialized(self) -> None:
        if not self._initialized:
            raise NotInitializedError("MemoryClient is not initialized. Call client.initialize() first.")


def _pick_first_provider_key(providers: MemoryProviderConfigs) -> str | None:
    for key, value in providers.items():
        if value is not None and key != "default":
            return key
    return None
