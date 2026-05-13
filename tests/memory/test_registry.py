"""Tests for the provider registry."""

from __future__ import annotations

import pytest

from atomicmemory.memory.provider import BaseMemoryProvider
from atomicmemory.memory.registry import (
    ProviderRegistration,
    ProviderRegistry,
)
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
    IngestResult,
    ListResultPage,
    Memory,
    SearchResultPage,
)


class _Stub(BaseMemoryProvider):
    name = "stub"

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(),
        )

    def do_ingest(self, input: object) -> IngestResult:  # type: ignore[override]
        return IngestResult()

    def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        return SearchResultPage()

    def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    def do_delete(self, ref: object) -> None:  # type: ignore[override]
        return None

    def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()


def test_register_and_get() -> None:
    registry = ProviderRegistry()
    registry.register("stub", lambda _cfg: ProviderRegistration(provider=_Stub()))

    factory = registry.get("stub")
    assert factory is not None
    assert factory({}).provider.name == "stub"


def test_register_rejects_duplicate() -> None:
    registry = ProviderRegistry()
    registry.register("stub", lambda _cfg: ProviderRegistration(provider=_Stub()))

    with pytest.raises(ValueError, match="already registered"):
        registry.register("stub", lambda _cfg: ProviderRegistration(provider=_Stub()))


def test_names_returns_sorted() -> None:
    registry = ProviderRegistry()
    registry.register("z", lambda _cfg: ProviderRegistration(provider=_Stub()))
    registry.register("a", lambda _cfg: ProviderRegistration(provider=_Stub()))

    assert registry.names() == ["a", "z"]


def test_contains() -> None:
    registry = ProviderRegistry()
    registry.register("stub", lambda _cfg: ProviderRegistration(provider=_Stub()))
    assert "stub" in registry
    assert "missing" not in registry
