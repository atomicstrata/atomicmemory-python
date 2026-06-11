"""Hierarchy and raise-site tests for the TS-parity error subclasses.

Non-breaking by construction: each subclass sits under the error Python
already raised at that site, so existing ``except ProviderError`` /
``except ValidationError`` handlers keep catching.
"""

from __future__ import annotations

import pytest

from atomicmemory import InvalidScopeError, UnsupportedOperationError
from atomicmemory.core.errors import ProviderError, ValidationError
from atomicmemory.memory.provider import BaseAsyncMemoryProvider, BaseMemoryProvider
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    AsyncProviderRegistry,
    ProviderRegistration,
    ProviderRegistry,
)
from atomicmemory.memory.service import AsyncMemoryService, MemoryService, MemoryServiceConfig
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
    IngestResult,
    ListResultPage,
    Memory,
    PackageRequest,
    Scope,
    SearchResultPage,
    TextIngest,
)

# ---------------------------------------------------------------------------
# Hierarchy tests
# ---------------------------------------------------------------------------


def test_unsupported_operation_is_a_provider_error() -> None:
    err = UnsupportedOperationError(provider="p", operation="package")
    assert isinstance(err, ProviderError)
    assert "p does not support package" in str(err)


def test_invalid_scope_is_a_validation_error() -> None:
    err = InvalidScopeError(provider="p", missing=["user", "namespace"], operation="ingest")
    assert isinstance(err, ValidationError)
    assert "requires scope fields: user, namespace" in str(err)


# ---------------------------------------------------------------------------
# Shared provider fakes
# ---------------------------------------------------------------------------


class _NoPackageProvider(BaseMemoryProvider):
    """Minimal provider with NO package extension."""

    name = "nopkg"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(),
        )

    def do_ingest(self, input: object) -> IngestResult:  # type: ignore[override]
        return IngestResult(created=["m1"])

    def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        return SearchResultPage()

    def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    def do_delete(self, ref: object) -> None:  # type: ignore[override]
        pass

    def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()


class _ScopeRequiredProvider(BaseMemoryProvider):
    """Provider that requires 'user' scope field."""

    name = "scoped"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(),
        )

    def do_ingest(self, input: object) -> IngestResult:  # type: ignore[override]
        return IngestResult(created=["m1"])

    def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        return SearchResultPage()

    def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    def do_delete(self, ref: object) -> None:  # type: ignore[override]
        pass

    def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()


# ---------------------------------------------------------------------------
# Sync package raise-site
# ---------------------------------------------------------------------------


def _make_sync_service(provider: BaseMemoryProvider) -> MemoryService:
    registry = ProviderRegistry()
    registry.register(provider.name, lambda _cfg: ProviderRegistration(provider=provider))
    service = MemoryService(
        MemoryServiceConfig(
            default_provider=provider.name,
            provider_configs={provider.name: {}},
        )
    )
    service.initialize(registry)
    return service


def test_sync_package_without_extension_raises_unsupported_operation() -> None:
    service = _make_sync_service(_NoPackageProvider())
    with pytest.raises(UnsupportedOperationError) as excinfo:
        service.package(PackageRequest(query="q", scope=Scope(user="u")))
    assert "nopkg does not support package" in str(excinfo.value)


def test_sync_package_unsupported_is_caught_by_provider_error() -> None:
    """Back-compat pin: existing ``except ProviderError`` handlers keep working."""
    service = _make_sync_service(_NoPackageProvider())
    caught = False
    try:
        service.package(PackageRequest(query="q", scope=Scope(user="u")))
    except ProviderError:
        caught = True
    assert caught


# ---------------------------------------------------------------------------
# Async package raise-site
# ---------------------------------------------------------------------------


class _AsyncNoPackageProvider(BaseAsyncMemoryProvider):
    """Minimal async provider (real base class) with NO package extension.

    Subclassing ``BaseAsyncMemoryProvider`` keeps the public ``ingest``
    wrapper — and therefore the async ``_validate_scope`` path — in play
    for the scope-validation raise-site tests below.
    """

    name = "async-nopkg"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(),
        )

    async def do_ingest(self, input: object) -> IngestResult:  # type: ignore[override]
        return IngestResult(created=["m1"])

    async def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        return SearchResultPage()

    async def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    async def do_delete(self, ref: object) -> None:  # type: ignore[override]
        pass

    async def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()


async def _make_async_service(provider: _AsyncNoPackageProvider) -> AsyncMemoryService:
    registry = AsyncProviderRegistry()
    registry.register(provider.name, lambda _cfg: AsyncProviderRegistration(provider=provider))
    service = AsyncMemoryService(
        MemoryServiceConfig(
            default_provider=provider.name,
            provider_configs={provider.name: {}},
        )
    )
    await service.initialize(registry)
    return service


async def test_async_package_without_extension_raises_unsupported_operation() -> None:
    service = await _make_async_service(_AsyncNoPackageProvider())
    with pytest.raises(UnsupportedOperationError) as excinfo:
        await service.package(PackageRequest(query="q", scope=Scope(user="u")))
    assert "async-nopkg does not support package" in str(excinfo.value)


async def test_async_package_unsupported_is_caught_by_provider_error() -> None:
    """Back-compat pin: existing ``except ProviderError`` handlers keep working."""
    service = await _make_async_service(_AsyncNoPackageProvider())
    caught = False
    try:
        await service.package(PackageRequest(query="q", scope=Scope(user="u")))
    except ProviderError:
        caught = True
    assert caught


# ---------------------------------------------------------------------------
# Scope validation raise-site
# ---------------------------------------------------------------------------


def test_missing_scope_fields_raise_invalid_scope() -> None:
    provider = _ScopeRequiredProvider()
    with pytest.raises(InvalidScopeError) as excinfo:
        provider.ingest(TextIngest(content="x", scope=Scope()))
    assert excinfo.value.context["missing"] == ["user"]


def test_invalid_scope_is_caught_by_validation_error() -> None:
    """Back-compat pin: existing ``except ValidationError`` handlers keep working."""
    provider = _ScopeRequiredProvider()
    caught = False
    try:
        provider.ingest(TextIngest(content="x", scope=Scope()))
    except ValidationError:
        caught = True
    assert caught


# BaseAsyncMemoryProvider._validate_scope is a distinct code path from the
# sync base class — cover it through the async service's ingest route.


async def test_async_missing_scope_fields_raise_invalid_scope() -> None:
    service = await _make_async_service(_AsyncNoPackageProvider())
    with pytest.raises(InvalidScopeError) as excinfo:
        await service.ingest(TextIngest(content="x", scope=Scope()))
    assert excinfo.value.context["missing"] == ["user"]


async def test_async_invalid_scope_is_caught_by_validation_error() -> None:
    """Back-compat pin: existing ``except ValidationError`` handlers keep working."""
    service = await _make_async_service(_AsyncNoPackageProvider())
    with pytest.raises(ValidationError):
        await service.ingest(TextIngest(content="x", scope=Scope()))
