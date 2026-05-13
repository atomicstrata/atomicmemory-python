"""Tests for atomicmemory.core.retry."""

from __future__ import annotations

import pytest

from atomicmemory.core.retry import RetryConfig, awith_retry, with_retry


def test_retry_config_validates_inputs() -> None:
    with pytest.raises(ValueError):
        RetryConfig(max_attempts=0)
    with pytest.raises(ValueError):
        RetryConfig(initial_delay_seconds=-1)
    with pytest.raises(ValueError):
        RetryConfig(initial_delay_seconds=2.0, max_delay_seconds=1.0)
    with pytest.raises(ValueError):
        RetryConfig(backoff_multiplier=0)


def test_with_retry_returns_first_success() -> None:
    sleeps: list[float] = []

    def fn() -> str:
        return "ok"

    result = with_retry(fn, sleep=sleeps.append)

    assert result == "ok"
    assert sleeps == []


def test_with_retry_respects_should_retry_predicate() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("transient")
        return "done"

    result = with_retry(
        fn,
        config=RetryConfig(max_attempts=3, initial_delay_seconds=0.1, max_delay_seconds=1.0),
        should_retry=lambda exc: isinstance(exc, TimeoutError),
        sleep=sleeps.append,
    )

    assert result == "done"
    assert attempts["n"] == 3
    assert sleeps == [0.1, 0.2]


def test_with_retry_reraises_when_predicate_rejects() -> None:
    sleeps: list[float] = []

    def fn() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        with_retry(fn, should_retry=lambda exc: isinstance(exc, TimeoutError), sleep=sleeps.append)
    assert sleeps == []


def test_with_retry_exhausts_attempts() -> None:
    sleeps: list[float] = []

    def fn() -> None:
        raise TimeoutError("forever")

    with pytest.raises(TimeoutError):
        with_retry(
            fn,
            config=RetryConfig(max_attempts=3, initial_delay_seconds=0.05, max_delay_seconds=1.0),
            should_retry=lambda _: True,
            sleep=sleeps.append,
        )
    assert sleeps == [0.05, 0.1]


@pytest.mark.asyncio
async def test_awith_retry_uses_async_sleep() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    async def fn() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise TimeoutError("transient")
        return "done"

    result = await awith_retry(
        fn,
        config=RetryConfig(max_attempts=2, initial_delay_seconds=0.1, max_delay_seconds=1.0),
        should_retry=lambda _: True,
        sleep=sleep,
    )
    assert result == "done"
    assert sleeps == [0.1]
