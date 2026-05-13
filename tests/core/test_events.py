"""Tests for atomicmemory.core.events.EventEmitter."""

from __future__ import annotations

import pytest

from atomicmemory.core.events import EventEmitter


def test_listeners_invoked_in_registration_order() -> None:
    emitter = EventEmitter()
    seen: list[int] = []
    emitter.on("ping", lambda v: seen.append(v))
    emitter.on("ping", lambda v: seen.append(v * 10))

    emitter.emit("ping", 3)

    assert seen == [3, 30]


def test_off_removes_listener() -> None:
    emitter = EventEmitter()
    seen: list[int] = []

    def listener(v: int) -> None:
        seen.append(v)

    emitter.on("ping", listener)
    emitter.off("ping", listener)
    emitter.emit("ping", 1)

    assert seen == []


def test_off_is_noop_for_unregistered_listener() -> None:
    emitter = EventEmitter()
    emitter.off("ping", lambda: None)


def test_emit_invokes_all_listeners_even_when_one_raises() -> None:
    emitter = EventEmitter()
    seen: list[str] = []

    def good(_: int) -> None:
        seen.append("good")

    def bad(_: int) -> None:
        raise RuntimeError("explode")

    emitter.on("ping", bad)
    emitter.on("ping", good)

    with pytest.raises(RuntimeError, match="explode"):
        emitter.emit("ping", 1)
    assert "good" in seen


def test_listener_count() -> None:
    emitter = EventEmitter()
    assert emitter.listener_count("ping") == 0
    emitter.on("ping", lambda: None)
    emitter.on("ping", lambda: None)
    assert emitter.listener_count("ping") == 2
    assert emitter.listener_count("other") == 0
