"""Retry primitives with exponential backoff.

Port of `atomicmemory-sdk/src/storage/retry-engine.ts`. Used by the HTTP
transports for idempotent operations (GET, search, list); never wrap
non-idempotent calls without a caller-supplied `should_retry` predicate.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Knobs for `with_retry`.

    Attributes:
        max_attempts: Total attempts, including the initial call. Must be
            ``>= 1``. ``1`` disables retry.
        initial_delay_seconds: Delay before the *second* attempt.
        max_delay_seconds: Upper bound on any single backoff delay.
        backoff_multiplier: Each successive delay is multiplied by this.
            ``2.0`` doubles the wait per attempt.
    """

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must be >= 0")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds must be >= initial_delay_seconds")
        if self.backoff_multiplier <= 0:
            raise ValueError("backoff_multiplier must be > 0")


def _delays(config: RetryConfig) -> list[float]:
    """Return the sequence of sleep durations between attempts."""
    delays: list[float] = []
    delay = config.initial_delay_seconds
    for _ in range(config.max_attempts - 1):
        delays.append(min(delay, config.max_delay_seconds))
        delay *= config.backoff_multiplier
    return delays


def with_retry(
    func: Callable[[], T],
    *,
    config: RetryConfig | None = None,
    should_retry: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run a callable with retry on transient failures.

    Args:
        func: Zero-argument callable to invoke.
        config: Retry configuration. Defaults to :class:`RetryConfig`'s
            defaults when ``None``.
        should_retry: Predicate that decides whether a given exception is
            transient. ``None`` means "never retry exceptions" — only
            useful for testing the success path.
        sleep: Sleep function. Pluggable for deterministic testing.

    Returns:
        Whatever ``func`` returns on its first successful attempt.

    Raises:
        BaseException: Re-raises the last exception if every attempt fails
            or if ``should_retry`` rejects it.
    """
    cfg = config or RetryConfig()
    delays = _delays(cfg)
    last_exc: BaseException | None = None
    for attempt in range(cfg.max_attempts):
        try:
            return func()
        except BaseException as exc:
            last_exc = exc
            is_last = attempt == cfg.max_attempts - 1
            if is_last or should_retry is None or not should_retry(exc):
                raise
            sleep(delays[attempt])
    assert last_exc is not None
    raise last_exc


async def awith_retry(
    func: Callable[[], Awaitable[T]],
    *,
    config: RetryConfig | None = None,
    should_retry: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Async counterpart of :func:`with_retry`.

    Behaviour mirrors the sync version; both use the same backoff schedule
    and the same predicate signature.
    """
    cfg = config or RetryConfig()
    delays = _delays(cfg)
    last_exc: BaseException | None = None
    for attempt in range(cfg.max_attempts):
        try:
            return await func()
        except BaseException as exc:
            last_exc = exc
            is_last = attempt == cfg.max_attempts - 1
            if is_last or should_retry is None or not should_retry(exc):
                raise
            await sleep(delays[attempt])
    assert last_exc is not None
    raise last_exc
