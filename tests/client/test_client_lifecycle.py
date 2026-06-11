"""Client-level lifecycle tests: concurrency, sticky failure, status consistency."""

from __future__ import annotations

import asyncio
import threading

import pytest

from atomicmemory import AsyncMemoryClient, MemoryClient
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    AsyncProviderRegistry,
    ProviderRegistration,
    ProviderRegistry,
)
from tests._lifecycle_fakes import _AsyncRecordingProvider, _RecordingProvider, _registry_ok_then_bad


def test_concurrent_initialize_runs_factories_once() -> None:
    calls = []

    def _factory(_cfg):  # type: ignore[no-untyped-def]
        calls.append(1)
        return ProviderRegistration(provider=_RecordingProvider())

    registry = ProviderRegistry()
    registry.register("p", _factory)
    client = MemoryClient(providers={"p": {}})
    threads = [threading.Thread(target=client.initialize, args=(registry,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_failed_initialize_is_sticky() -> None:
    calls = []

    def _bad(_cfg):  # type: ignore[no-untyped-def]
        calls.append(1)
        raise RuntimeError("boom")

    registry = ProviderRegistry()
    registry.register("p", _bad)
    client = MemoryClient(providers={"p": {}})
    with pytest.raises(RuntimeError, match="boom"):
        client.initialize(registry)
    with pytest.raises(RuntimeError, match="boom"):
        client.initialize(registry)
    assert len(calls) == 1


def test_provider_status_consistent_after_failed_initialize() -> None:
    registry = _registry_ok_then_bad(_RecordingProvider())
    client = MemoryClient(providers={"ok": {}, "bad": {}})
    with pytest.raises(RuntimeError):
        client.initialize(registry)
    assert all(not s.initialized for s in client.get_provider_status())


def test_sync_first_registry_wins() -> None:
    # A second thread races with a BAD registry while the first (good, slow)
    # run holds the lock — the bad factory must never be invoked.
    bad_calls = []
    good_entered = threading.Event()
    release_good = threading.Event()

    def _slow_good(_cfg: object) -> ProviderRegistration:
        good_entered.set()
        assert release_good.wait(timeout=5)
        return ProviderRegistration(provider=_RecordingProvider())

    def _bad(_cfg: object) -> ProviderRegistration:
        bad_calls.append(1)
        raise RuntimeError("must not run")

    good, bad = ProviderRegistry(), ProviderRegistry()
    good.register("p", _slow_good)
    bad.register("p", _bad)
    client = MemoryClient(providers={"p": {}})
    t_good = threading.Thread(target=client.initialize, args=(good,))
    t_good.start()
    assert good_entered.wait(timeout=5)  # good run owns the lock before bad starts
    t_bad = threading.Thread(target=client.initialize, args=(bad,))
    t_bad.start()
    release_good.set()
    t_good.join()
    t_bad.join()
    assert bad_calls == []
    assert all(s.initialized for s in client.get_provider_status())


def test_close_then_initialize_reopens() -> None:
    registry = ProviderRegistry()
    registry.register("p", lambda _cfg: ProviderRegistration(provider=_RecordingProvider()))
    client = MemoryClient(providers={"p": {}})
    client.initialize(registry)
    client.close()
    client.initialize(registry)  # successful lifecycle stays re-openable
    assert all(s.initialized for s in client.get_provider_status())


# ---------------------------------------------------------------------------
# Async client lifecycle tests
# ---------------------------------------------------------------------------


async def test_async_concurrent_initialize_runs_factories_once() -> None:
    calls: list[int] = []

    async def _factory(_cfg: object) -> AsyncProviderRegistration:
        calls.append(1)
        await asyncio.sleep(0.02)
        return AsyncProviderRegistration(provider=_AsyncRecordingProvider())

    registry = AsyncProviderRegistry()
    registry.register("p", _factory)
    client = AsyncMemoryClient(providers={"p": {}})
    await asyncio.gather(*(client.initialize(registry) for _ in range(8)))
    assert len(calls) == 1


async def test_async_failed_initialize_is_sticky() -> None:
    calls: list[int] = []

    def _bad(_cfg: object) -> AsyncProviderRegistration:
        calls.append(1)
        raise RuntimeError("boom")

    registry = AsyncProviderRegistry()
    registry.register("p", _bad)
    client = AsyncMemoryClient(providers={"p": {}})
    with pytest.raises(RuntimeError, match="boom"):
        await client.initialize(registry)
    with pytest.raises(RuntimeError, match="boom"):
        await client.initialize(registry)
    assert len(calls) == 1


async def test_cancelled_waiter_does_not_poison_shared_initialize() -> None:
    # One waiter is cancelled mid-run; the shared run continues, a second
    # waiter completes, factory ran once, client is initialized. Event
    # barriers make the ordering deterministic (no sleep-based timing).
    calls: list[int] = []
    entered, gate = asyncio.Event(), asyncio.Event()

    async def _gated(_cfg: object) -> AsyncProviderRegistration:
        calls.append(1)
        entered.set()
        await gate.wait()
        return AsyncProviderRegistration(provider=_AsyncRecordingProvider())

    registry = AsyncProviderRegistry()
    registry.register("p", _gated)
    client = AsyncMemoryClient(providers={"p": {}})
    waiter = asyncio.ensure_future(client.initialize(registry))
    await entered.wait()  # the shared run is definitely in-flight
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    gate.set()
    await client.initialize(registry)  # shares the surviving run
    assert len(calls) == 1
    assert all(s.initialized for s in client.get_provider_status())


async def test_async_first_registry_wins() -> None:
    # Second caller passes a BAD registry while the first (good) run is
    # provably pending (Event barrier) — the bad factory must never be
    # invoked; init succeeds with the first registry's provider.
    bad_calls: list[int] = []
    entered, gate = asyncio.Event(), asyncio.Event()

    async def _gated_good(_cfg: object) -> AsyncProviderRegistration:
        entered.set()
        await gate.wait()
        return AsyncProviderRegistration(provider=_AsyncRecordingProvider())

    def _bad(_cfg: object) -> AsyncProviderRegistration:
        bad_calls.append(1)
        raise RuntimeError("must not run")

    good, bad = AsyncProviderRegistry(), AsyncProviderRegistry()
    good.register("p", _gated_good)
    bad.register("p", _bad)
    client = AsyncMemoryClient(providers={"p": {}})
    first = asyncio.ensure_future(client.initialize(good))
    await entered.wait()  # good run owns _init_task before bad arrives
    second = asyncio.ensure_future(client.initialize(bad))
    gate.set()
    await asyncio.gather(first, second)
    assert bad_calls == []


async def test_close_during_pending_initialize_cancels_and_ends_uninitialized() -> None:
    # Cancellation lands in the FACTORY phase (Event barrier, deterministic).
    calls: list[int] = []
    entered = asyncio.Event()

    async def _gated(_cfg: object) -> AsyncProviderRegistration:
        calls.append(1)
        entered.set()
        await asyncio.Event().wait()  # blocks until the run is cancelled
        return AsyncProviderRegistration(provider=_AsyncRecordingProvider())

    registry = AsyncProviderRegistry()
    registry.register("p", _gated)
    client = AsyncMemoryClient(providers={"p": {}})
    waiter = asyncio.ensure_future(client.initialize(registry))
    await entered.wait()  # the init run is provably in-flight
    await client.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert all(not s.initialized for s in client.get_provider_status())
    fresh = AsyncProviderRegistry()
    fresh.register("p", lambda _cfg: AsyncProviderRegistration(provider=_AsyncRecordingProvider()))
    await client.initialize(fresh)  # cancellation is not sticky — fresh run allowed
    assert len(calls) == 1


async def test_close_during_provider_initialize_tears_down_staged_provider() -> None:
    # Cancellation lands in the PROVIDER-INITIALIZE phase: the provider is
    # already STAGED, so this exercises the service's staged-init teardown
    # (gathered close) that the factory-phase test above cannot reach.
    init_started = asyncio.Event()
    blocked = _AsyncRecordingProvider(init_started=init_started, init_gate=asyncio.Event())
    registry = AsyncProviderRegistry()
    registry.register("p", lambda _cfg: AsyncProviderRegistration(provider=blocked))
    client = AsyncMemoryClient(providers={"p": {}})
    waiter = asyncio.ensure_future(client.initialize(registry))
    await init_started.wait()  # provider.initialize() is blocked → provider IS staged
    await client.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert blocked.close_calls == 1  # staged-init teardown closed it
    assert all(not s.initialized for s in client.get_provider_status())


async def test_reinitialize_after_orphaned_success_then_close() -> None:
    # All waiters cancelled; the run SUCCEEDS unobserved; close(); re-initialize
    # must run a FRESH initialization (the stale done task must not satisfy it).
    entered, gate = asyncio.Event(), asyncio.Event()
    calls: list[int] = []

    async def _gated(_cfg: object) -> AsyncProviderRegistration:
        calls.append(1)
        entered.set()
        await gate.wait()
        return AsyncProviderRegistration(provider=_AsyncRecordingProvider())

    registry = AsyncProviderRegistry()
    registry.register("p", _gated)
    client = AsyncMemoryClient(providers={"p": {}})
    waiter = asyncio.ensure_future(client.initialize(registry))
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    gate.set()
    await asyncio.sleep(0)  # let the orphaned run complete successfully
    assert all(s.initialized for s in client.get_provider_status())
    await client.close()
    await client.initialize(registry)  # must be a FRESH run, not the stale task
    assert len(calls) == 2
    assert all(s.initialized for s in client.get_provider_status())


async def test_orphaned_failed_run_stays_sticky_without_waiters() -> None:
    # All waiters cancelled, then the unobserved run FAILS: the outcome must
    # still be recorded sticky (and the task's exception retrieved so asyncio
    # never logs "Task exception was never retrieved").
    entered, gate = asyncio.Event(), asyncio.Event()
    calls: list[int] = []

    async def _failing(_cfg: object) -> AsyncProviderRegistration:
        calls.append(1)
        entered.set()
        await gate.wait()
        raise RuntimeError("boom")

    registry = AsyncProviderRegistry()
    registry.register("p", _failing)
    client = AsyncMemoryClient(providers={"p": {}})
    waiter = asyncio.ensure_future(client.initialize(registry))
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    gate.set()
    await asyncio.sleep(0)  # let the orphaned run fail unobserved
    with pytest.raises(RuntimeError, match="boom"):
        await client.initialize(registry)  # sticky error, no fresh run
    assert len(calls) == 1


def test_async_failed_outcome_is_observable_from_another_loop() -> None:
    # Loop-independence of the COMPLETED outcome (spec §3.2): fail in loop 1,
    # observe the same sticky error from loop 2. (A still-PENDING init is
    # loop-bound and unsupported cross-loop — documented, not tested.)
    registry = AsyncProviderRegistry()

    def _bad(_cfg: object) -> AsyncProviderRegistration:
        raise RuntimeError("boom")

    registry.register("p", _bad)
    client = AsyncMemoryClient(providers={"p": {}})
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(client.initialize(registry))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(client.initialize(registry))
