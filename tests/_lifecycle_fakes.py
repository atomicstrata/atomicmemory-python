"""Shared fake providers and registry helpers for lifecycle tests.

Task 2 creates _RecordingProvider and _registry_ok_then_bad here.
Task 3 adds _AsyncRecordingProvider.
Both tests/memory/test_service_lifecycle.py and
tests/client/test_client_lifecycle.py import from this module.
"""

from __future__ import annotations

import asyncio

from atomicmemory.memory.provider import BaseAsyncMemoryProvider, BaseMemoryProvider
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    AsyncProviderRegistry,
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


class _RecordingProvider(BaseMemoryProvider):
    """Minimal provider mirroring test_service.py's _Recorder; records close()."""

    def __init__(self, close_raises: bool = False, init_raises: bool = False) -> None:
        self.name = "recording"
        self.close_calls = 0
        self._close_raises = close_raises
        self._init_raises = init_raises

    def initialize(self) -> None:
        if self._init_raises:
            raise RuntimeError("init failed")

    def close(self) -> None:
        self.close_calls += 1
        if self._close_raises:
            raise RuntimeError("close failed")

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(package=False),
        )

    def do_ingest(self, input: object) -> IngestResult:  # type: ignore[override]
        return IngestResult(created=[])

    def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        return SearchResultPage()

    def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    def do_delete(self, ref: object) -> None:  # type: ignore[override]
        return None

    def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()


def _registry_ok_then_bad(ok_provider: _RecordingProvider) -> ProviderRegistry:
    """Build a registry whose 'ok' factory succeeds and 'bad' factory raises."""
    registry = ProviderRegistry()
    registry.register("ok", lambda _cfg: ProviderRegistration(provider=ok_provider))

    def _bad(_cfg: object) -> ProviderRegistration:
        raise RuntimeError("boom")

    registry.register("bad", _bad)
    return registry


class _AsyncRecordingProvider(BaseAsyncMemoryProvider):
    """Async counterpart to _RecordingProvider; records close() calls.

    Optional Event knobs for Task 5 cancellation tests:
    - ``init_started``: set at entry to ``initialize()`` so waiters can
      synchronize on the provider being mid-init.
    - ``init_gate``: awaited in ``initialize()`` when provided, blocking
      until the caller sets it (or the run is cancelled).
    """

    def __init__(
        self,
        close_raises: bool = False,
        init_raises: bool = False,
        init_started: asyncio.Event | None = None,
        init_gate: asyncio.Event | None = None,
    ) -> None:
        self.name = "async-recording"
        self.close_calls = 0
        self._close_raises = close_raises
        self._init_raises = init_raises
        self._init_started = init_started
        self._init_gate = init_gate

    async def initialize(self) -> None:
        if self._init_started is not None:
            self._init_started.set()
        if self._init_gate is not None:
            await self._init_gate.wait()
        if self._init_raises:
            raise RuntimeError("init failed")

    async def close(self) -> None:
        self.close_calls += 1
        if self._close_raises:
            raise RuntimeError("close failed")

    def capabilities(self) -> Capabilities:
        return Capabilities(
            ingest_modes=["text"],
            required_scope=CapabilitiesRequiredScope(default=["user"]),
            extensions=CapabilitiesExtensions(package=False),
        )

    async def do_ingest(self, input: object) -> IngestResult:  # type: ignore[override]
        return IngestResult(created=[])

    async def do_search(self, request: object) -> SearchResultPage:  # type: ignore[override]
        return SearchResultPage()

    async def do_get(self, ref: object) -> Memory | None:  # type: ignore[override]
        return None

    async def do_delete(self, ref: object) -> None:  # type: ignore[override]
        return None

    async def do_list(self, request: object) -> ListResultPage:  # type: ignore[override]
        return ListResultPage()


def _async_registry_ok_then_bad(ok_provider: _AsyncRecordingProvider) -> AsyncProviderRegistry:
    """Build an async registry whose 'ok' factory succeeds and 'bad' factory raises."""
    registry = AsyncProviderRegistry()
    registry.register("ok", lambda _cfg: AsyncProviderRegistration(provider=ok_provider))

    async def _bad(_cfg: object) -> AsyncProviderRegistration:
        raise RuntimeError("boom")

    registry.register("bad", _bad)
    return registry
