"""Tests for the sync BaseMemoryProvider — scope validation + error wrapping."""

from __future__ import annotations

import pytest

from atomicmemory.core.errors import NotInitializedError, ProviderError, ValidationError
from atomicmemory.memory.provider import BaseMemoryProvider
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
    IngestResult,
    ListResultPage,
    Memory,
    Scope,
    SearchResultPage,
    TextIngest,
)


class _FakeProvider(BaseMemoryProvider):
    name = "fake"

    def __init__(self, *, ready: bool = True) -> None:
        self._initialized = ready
        self.calls: list[str] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text", "messages"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(),
        )

    def do_ingest(self, input: TextIngest) -> IngestResult:  # type: ignore[override]
        self.calls.append("ingest")
        return IngestResult(created=["m1"])

    def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        self.calls.append("search")
        return SearchResultPage()

    def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        self.calls.append("get")
        return None

    def do_delete(self, ref: object) -> None:  # type: ignore[override]
        self.calls.append("delete")

    def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        self.calls.append("list")
        return ListResultPage()


def test_ingest_validates_scope_user_required() -> None:
    provider = _FakeProvider()
    bad_input = TextIngest(content="x", scope=Scope())

    with pytest.raises(ValidationError) as excinfo:
        provider.ingest(bad_input)
    assert "user" in excinfo.value.context["missing"]


def test_ingest_succeeds_with_valid_scope() -> None:
    provider = _FakeProvider()
    result = provider.ingest(TextIngest(content="x", scope=Scope(user="u1")))

    assert result.created == ["m1"]
    assert provider.calls == ["ingest"]


def test_uninitialized_provider_raises() -> None:
    provider = _FakeProvider(ready=False)

    with pytest.raises(NotInitializedError):
        provider.ingest(TextIngest(content="x", scope=Scope(user="u1")))


def test_unexpected_exception_wrapped_in_provider_error() -> None:
    class Boom(_FakeProvider):
        def do_ingest(self, input: TextIngest) -> IngestResult:  # type: ignore[override]
            raise RuntimeError("kaboom")

    provider = Boom()

    with pytest.raises(ProviderError) as excinfo:
        provider.ingest(TextIngest(content="x", scope=Scope(user="u1")))
    assert excinfo.value.provider == "fake"
    assert "kaboom" in excinfo.value.message


def test_get_extension_returns_self_for_supported_extension() -> None:
    class WithPackage(_FakeProvider):
        def capabilities(self) -> Capabilities:
            return Capabilities(
                ingest_modes=["text"],
                required_scope=CapabilitiesRequiredScope(default=["user"]),
                extensions=CapabilitiesExtensions(package=True),
            )

    provider = WithPackage()
    assert provider.get_extension("package") is provider
    assert provider.get_extension("temporal") is None
