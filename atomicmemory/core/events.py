"""Lightweight typed event emitter.

Port of `atomicmemory-sdk/src/core/events.ts`. Sync-only by design — the
SDK emits events for cache hits, search completions, and similar
diagnostic hooks; async listeners can schedule themselves via the event
loop if needed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Listener = Callable[..., None]


class EventEmitter:
    """Minimal pub/sub for diagnostic events.

    Not thread-safe. Listeners are invoked synchronously in registration
    order; an exception in one listener does not prevent the others from
    running, but the first exception is re-raised after all have been
    called.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = {}

    def on(self, event: str, listener: Listener) -> None:
        """Register a listener for ``event``."""
        self._listeners.setdefault(event, []).append(listener)

    def off(self, event: str, listener: Listener) -> None:
        """Remove a previously registered listener.

        No-op when the listener was not registered.
        """
        if event not in self._listeners:
            return
        try:
            self._listeners[event].remove(listener)
        except ValueError:
            return

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Invoke every listener registered for ``event``.

        Raises:
            BaseException: Re-raises the first listener exception after
                all listeners have been invoked.
        """
        listeners = list(self._listeners.get(event, ()))
        first_exc: BaseException | None = None
        for listener in listeners:
            try:
                listener(*args, **kwargs)
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc
        if first_exc is not None:
            raise first_exc

    def listener_count(self, event: str) -> int:
        """Number of listeners registered for ``event``."""
        return len(self._listeners.get(event, ()))
