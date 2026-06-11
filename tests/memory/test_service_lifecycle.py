"""Lifecycle tests for MemoryService and AsyncMemoryService initialize semantics.

Verifies atomic staged registration, best-effort teardown on failure,
ConfigError when the default provider has no factory, and correct
state reset across close → re-initialize cycles — for both the sync
and async service surfaces.
"""

from __future__ import annotations

import asyncio

import pytest

from atomicmemory.core.errors import ConfigError
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    AsyncProviderRegistry,
    ProviderRegistration,
    ProviderRegistry,
)
from atomicmemory.memory.service import AsyncMemoryService, MemoryService, MemoryServiceConfig
from tests._lifecycle_fakes import (
    _async_registry_ok_then_bad,
    _AsyncRecordingProvider,
    _RecordingProvider,
    _registry_ok_then_bad,
)


def test_failed_initialize_leaves_no_partial_state() -> None:
    ok = _RecordingProvider()
    svc = MemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "bad": {}}))
    with pytest.raises(RuntimeError, match="boom"):
        svc.initialize(_registry_ok_then_bad(ok))
    assert svc.get_available_providers() == []


def test_failed_initialize_tears_down_staged_providers() -> None:
    ok = _RecordingProvider()
    svc = MemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "bad": {}}))
    with pytest.raises(RuntimeError):
        svc.initialize(_registry_ok_then_bad(ok))
    assert ok.close_calls == 1


def test_failure_inside_provider_initialize_tears_down_prior_providers() -> None:
    ok = _RecordingProvider()
    bad_init = _RecordingProvider(init_raises=True)
    registry = ProviderRegistry()
    registry.register("ok", lambda _cfg: ProviderRegistration(provider=ok))
    registry.register("bad", lambda _cfg: ProviderRegistration(provider=bad_init))
    svc = MemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "bad": {}}))
    with pytest.raises(RuntimeError, match="init failed"):
        svc.initialize(registry)
    assert svc.get_available_providers() == []
    assert ok.close_calls == 1
    assert bad_init.close_calls == 1  # bad was STAGED before its initialize raised


def test_teardown_failure_does_not_mask_original_error() -> None:
    ok = _RecordingProvider(close_raises=True)
    svc = MemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "bad": {}}))
    with pytest.raises(RuntimeError, match="boom"):
        svc.initialize(_registry_ok_then_bad(ok))


def test_initialize_fails_when_default_provider_has_no_factory() -> None:
    registry = ProviderRegistry()
    registry.register("other", lambda _cfg: ProviderRegistration(provider=_RecordingProvider()))
    svc = MemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "other": {}}))
    with pytest.raises(ConfigError, match="ok"):
        svc.initialize(registry)
    assert svc.get_available_providers() == []


def test_best_effort_close_runs_all_providers_and_reraises() -> None:
    p1, p2 = _RecordingProvider(close_raises=True), _RecordingProvider()
    svc = MemoryService(MemoryServiceConfig(default_provider="p1", provider_configs={"p1": {}, "p2": {}}))
    reg = ProviderRegistry()
    reg.register("p1", lambda _cfg: ProviderRegistration(provider=p1))
    reg.register("p2", lambda _cfg: ProviderRegistration(provider=p2))
    svc.initialize(reg)
    with pytest.raises(RuntimeError, match="close failed"):
        svc.close()
    assert p2.close_calls == 1
    assert svc.get_available_providers() == []


def test_reinitialize_after_close_drops_old_providers() -> None:
    first, second = _RecordingProvider(), _RecordingProvider()
    reg_a, reg_b = ProviderRegistry(), ProviderRegistry()
    reg_a.register("ok", lambda _cfg: ProviderRegistration(provider=first))
    reg_a.register("other", lambda _cfg: ProviderRegistration(provider=_RecordingProvider()))
    reg_b.register("other", lambda _cfg: ProviderRegistration(provider=second))
    svc = MemoryService(MemoryServiceConfig(default_provider="other", provider_configs={"ok": {}, "other": {}}))
    svc.initialize(reg_a)
    svc.close()
    svc.initialize(reg_b)
    assert svc.get_available_providers() == ["other"]


# ---------------------------------------------------------------------------
# Async service lifecycle tests
# ---------------------------------------------------------------------------


async def test_async_factory_returning_awaitable_is_awaited() -> None:
    ok = _AsyncRecordingProvider()
    registry = AsyncProviderRegistry()

    async def _factory(_cfg: object) -> AsyncProviderRegistration:
        return AsyncProviderRegistration(provider=ok)

    registry.register("ok", _factory)
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}}))
    await svc.initialize(registry)
    assert svc.get_provider("ok") is ok


async def test_async_sync_factories_still_work() -> None:
    ok = _AsyncRecordingProvider()
    registry = AsyncProviderRegistry()
    registry.register("ok", lambda _cfg: AsyncProviderRegistration(provider=ok))
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}}))
    await svc.initialize(registry)
    assert svc.get_provider("ok") is ok


async def test_async_failed_initialize_is_atomic_with_teardown() -> None:
    # Exercise init_started to keep vulture from flagging it as unused before Task 5.
    init_started = asyncio.Event()
    ok = _AsyncRecordingProvider(init_started=init_started)
    registry = _async_registry_ok_then_bad(ok)
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "bad": {}}))
    with pytest.raises(RuntimeError, match="boom"):
        await svc.initialize(registry)
    assert init_started.is_set()  # init_started was set during ok's initialize
    assert svc.get_available_providers() == []
    assert ok.close_calls == 1


async def test_async_failure_inside_provider_initialize_tears_down_prior_providers() -> None:
    ok = _AsyncRecordingProvider()
    bad_init = _AsyncRecordingProvider(init_raises=True)
    registry = AsyncProviderRegistry()
    registry.register("ok", lambda _cfg: AsyncProviderRegistration(provider=ok))
    registry.register("bad", lambda _cfg: AsyncProviderRegistration(provider=bad_init))
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "bad": {}}))
    with pytest.raises(RuntimeError, match="init failed"):
        await svc.initialize(registry)
    assert svc.get_available_providers() == []
    assert ok.close_calls == 1
    assert bad_init.close_calls == 1  # bad was STAGED before its initialize raised


async def test_async_initialize_fails_when_default_provider_has_no_factory() -> None:
    registry = AsyncProviderRegistry()
    registry.register("other", lambda _cfg: AsyncProviderRegistration(provider=_AsyncRecordingProvider()))
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="ok", provider_configs={"ok": {}, "other": {}}))
    with pytest.raises(ConfigError, match="ok"):
        await svc.initialize(registry)
    assert svc.get_available_providers() == []


async def test_async_best_effort_close_runs_all_providers_and_reraises() -> None:
    p1, p2 = _AsyncRecordingProvider(close_raises=True), _AsyncRecordingProvider()
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="p1", provider_configs={"p1": {}, "p2": {}}))
    reg = AsyncProviderRegistry()
    reg.register("p1", lambda _cfg: AsyncProviderRegistration(provider=p1))
    reg.register("p2", lambda _cfg: AsyncProviderRegistration(provider=p2))
    await svc.initialize(reg)
    with pytest.raises(RuntimeError, match="close failed"):
        await svc.close()
    assert p2.close_calls == 1
    assert svc.get_available_providers() == []


async def test_async_reinitialize_after_close_drops_old_providers() -> None:
    reg_a, reg_b = AsyncProviderRegistry(), AsyncProviderRegistry()
    reg_a.register("ok", lambda _cfg: AsyncProviderRegistration(provider=_AsyncRecordingProvider()))
    reg_a.register("other", lambda _cfg: AsyncProviderRegistration(provider=_AsyncRecordingProvider()))
    reg_b.register("other", lambda _cfg: AsyncProviderRegistration(provider=_AsyncRecordingProvider()))
    svc = AsyncMemoryService(MemoryServiceConfig(default_provider="other", provider_configs={"ok": {}, "other": {}}))
    await svc.initialize(reg_a)
    await svc.close()
    await svc.initialize(reg_b)
    assert svc.get_available_providers() == ["other"]
