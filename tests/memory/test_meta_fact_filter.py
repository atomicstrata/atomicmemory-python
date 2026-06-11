"""Tests for the opt-in meta-fact filter (parity with the TS SDK)."""

from __future__ import annotations

import re

from atomicmemory.memory.meta_fact_filter import (
    DEFAULT_META_FACT_PATTERNS,
    MetaFactFilterConfig,
    filter_meta_facts,
    is_meta_fact,
    resolve_meta_fact_patterns,
)

_META = "The user asked for the user's name."
_REAL = "Dana prefers concise technical answers."


def _content(item: dict[str, str]) -> str:
    return item["content"]


def test_is_meta_fact_matches_defaults_and_rejects_real_facts() -> None:
    assert is_meta_fact(_META) is True
    assert is_meta_fact("A name was mentioned in the chat.") is True
    assert is_meta_fact(_REAL) is False
    assert is_meta_fact("") is False
    assert is_meta_fact(None) is False  # type: ignore[arg-type]


def test_disabled_filter_passes_everything_through() -> None:
    items = [{"content": _META}, {"content": _REAL}]
    out = filter_meta_facts(items, _content, MetaFactFilterConfig(enabled=False))
    assert out == items


def test_enabled_filter_drops_meta_facts_keeps_real() -> None:
    items = [{"content": _META}, {"content": _REAL}]
    out = filter_meta_facts(items, _content, MetaFactFilterConfig(enabled=True))
    assert out == [{"content": _REAL}]


def test_custom_patterns_replace_defaults() -> None:
    cfg = MetaFactFilterConfig(enabled=True, patterns=[re.compile(r"^drop me", re.IGNORECASE)])
    items = [{"content": "DROP ME now"}, {"content": _META}]
    out = filter_meta_facts(items, _content, cfg)
    # Only the custom pattern applies; the default meta-fact survives.
    assert out == [{"content": _META}]


def test_extend_mode_unions_custom_and_defaults() -> None:
    cfg = MetaFactFilterConfig(enabled=True, patterns=[re.compile(r"^drop me", re.IGNORECASE)], mode="extend")
    items = [{"content": "DROP ME"}, {"content": _META}, {"content": _REAL}]
    out = filter_meta_facts(items, _content, cfg)
    assert out == [{"content": _REAL}]


def test_on_drop_callback_invoked_per_drop() -> None:
    dropped: list[tuple[str, int]] = []
    cfg = MetaFactFilterConfig(enabled=True, on_drop=lambda c, i: dropped.append((c, i)))
    filter_meta_facts([{"content": _META}], _content, cfg)
    assert dropped == [(_META, 0)]


def test_on_drop_exception_is_swallowed() -> None:
    def boom(_c: str, _i: int) -> None:
        raise RuntimeError("telemetry down")

    cfg = MetaFactFilterConfig(enabled=True, on_drop=boom)
    # Must not raise; recall continues even if telemetry fails.
    out = filter_meta_facts([{"content": _META}, {"content": _REAL}], _content, cfg)
    assert out == [{"content": _REAL}]


def test_resolve_patterns_replace_and_extend() -> None:
    custom = [re.compile(r"^x")]
    assert resolve_meta_fact_patterns(MetaFactFilterConfig(enabled=True)) == DEFAULT_META_FACT_PATTERNS
    assert resolve_meta_fact_patterns(MetaFactFilterConfig(enabled=True, patterns=custom)) == tuple(custom)
    extended = resolve_meta_fact_patterns(MetaFactFilterConfig(enabled=True, patterns=custom, mode="extend"))
    assert extended == (*custom, *DEFAULT_META_FACT_PATTERNS)
