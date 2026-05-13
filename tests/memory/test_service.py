"""Tests for MemoryService routing + initialization."""

from __future__ import annotations

import pytest

from atomicmemory.core.errors import ConfigError, ProviderError
from atomicmemory.memory.provider import BaseMemoryProvider
from atomicmemory.memory.registry import ProviderRegistration, ProviderRegistry
from atomicmemory.memory.service import MemoryService, MemoryServiceConfig
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


class _Recorder(BaseMemoryProvider):
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []
        self._initialized = True

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(package=True),
        )

    def do_ingest(self, input: TextIngest) -> IngestResult:  # type: ignore[override]
        self.calls.append(f"ingest:{self.name}")
        return IngestResult(created=[f"m-{self.name}"])

    def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        self.calls.append(f"search:{self.name}")
        return SearchResultPage()

    def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    def do_delete(self, ref: object) -> None:  # type: ignore[override]
        return None

    def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()

    def package(self, request: PackageRequest) -> object:  # type: ignore[override]
        self.calls.append(f"package:{self.name}")
        return {"text": "", "results": [], "tokens": 0}


def _make_service(default: str = "a") -> tuple[MemoryService, _Recorder, _Recorder]:
    registry = ProviderRegistry()
    a, b = _Recorder("a"), _Recorder("b")
    registry.register("a", lambda _cfg: ProviderRegistration(provider=a))
    registry.register("b", lambda _cfg: ProviderRegistration(provider=b))
    service = MemoryService(MemoryServiceConfig(default_provider=default, provider_configs={"a": {}, "b": {}}))
    service.initialize(registry)
    return service, a, b


def test_routes_to_default_provider() -> None:
    service, a, _ = _make_service()
    service.ingest(TextIngest(content="x", scope=Scope(user="u")))
    assert "ingest:a" in a.calls


def test_routes_to_named_provider() -> None:
    service, _, b = _make_service()
    service.ingest(TextIngest(content="x", scope=Scope(user="u")), provider_name="b")
    assert "ingest:b" in b.calls


def test_unknown_provider_raises() -> None:
    service, _, _ = _make_service()
    with pytest.raises(ConfigError):
        service.ingest(TextIngest(content="x", scope=Scope(user="u")), provider_name="missing")


def test_default_must_exist_in_provider_configs() -> None:
    with pytest.raises(ConfigError):
        MemoryService(MemoryServiceConfig(default_provider="ghost", provider_configs={"a": {}}))


def test_package_requires_extension() -> None:
    class NoPackager(_Recorder):
        def capabilities(self) -> Capabilities:
            return Capabilities(
                ingest_modes=["text"],
                required_scope=CapabilitiesRequiredScope(default=["user"]),
                extensions=CapabilitiesExtensions(),
            )

    registry = ProviderRegistry()
    p = NoPackager("a")
    registry.register("a", lambda _cfg: ProviderRegistration(provider=p))
    service = MemoryService(MemoryServiceConfig(default_provider="a", provider_configs={"a": {}}))
    service.initialize(registry)

    with pytest.raises(ProviderError, match="does not support"):
        service.package(PackageRequest(query="q", scope=Scope(user="u")))
