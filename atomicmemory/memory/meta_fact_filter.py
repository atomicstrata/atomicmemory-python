"""Meta-fact filter.

Post-retrieval filter that drops "meta-facts" -- extraction artifacts that
describe the conversation itself ("The user asked for the user's name.", "As of
<date>, X is a term mentioned in the conversation.") rather than recording a
durable fact about the user. When such artifacts sit in the recall pool they
can outrank real user facts at thin cosine margins, so removing them lifts
recall quality.

Port of ``atomicmemory-sdk/src/memory/meta-fact-filter.ts``. The filter is
intentionally pure (deterministic regex application, no I/O), opt-in (off unless
explicitly enabled in provider config), case-insensitive, and additive (apps may
add patterns without losing the defaults).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, TypeVar

from atomicmemory.core.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)

# Built-in patterns observed in real partner demos. Each is matched
# case-insensitively against the memory content; a match drops the memory.
DEFAULT_META_FACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*the user (asked|requested|said|is asking|is me)\b", re.IGNORECASE),
    re.compile(
        r"^\s*as of [^,]+,\s+.+\s+is a term mentioned in the conversation\.?$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*a name was mentioned\b", re.IGNORECASE),
    re.compile(r"^\s*the conversation involves the user\b", re.IGNORECASE),
    re.compile(r"^\s*the user has started a conversation\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class MetaFactFilterConfig:
    """Configuration for the opt-in meta-fact filter.

    Attributes:
        enabled: Master switch. When ``False`` (the default for the provider,
            which leaves this config unset) the filter is a no-op. Not inferred
            from the environment, to keep behavior deterministic.
        patterns: Patterns matched against ``memory.content``. When ``None`` the
            built-in :data:`DEFAULT_META_FACT_PATTERNS` are used.
        mode: How ``patterns`` interacts with the defaults. ``"replace"`` (the
            default) uses only the provided patterns; ``"extend"`` applies the
            provided patterns *and* the defaults.
        on_drop: Optional callback invoked once per dropped result with
            ``(content, pattern_index)``. Exceptions it raises are swallowed so
            telemetry can never break recall.
    """

    enabled: bool
    patterns: Sequence[re.Pattern[str]] | None = None
    mode: Literal["replace", "extend"] = "replace"
    on_drop: Callable[[str, int], None] | None = None


def resolve_meta_fact_patterns(config: MetaFactFilterConfig) -> tuple[re.Pattern[str], ...]:
    """Resolve the effective pattern list for a config. Pure; safe to repeat."""
    if config.patterns is None:
        return DEFAULT_META_FACT_PATTERNS
    if config.mode == "extend":
        return (*config.patterns, *DEFAULT_META_FACT_PATTERNS)
    return tuple(config.patterns)


def is_meta_fact(
    content: object,
    patterns: Sequence[re.Pattern[str]] = DEFAULT_META_FACT_PATTERNS,
) -> bool:
    """Return ``True`` when ``content`` matches any pattern.

    Defensive against non-string input (returns ``False``) so a malformed
    result cannot crash the filter pipeline.
    """
    if not isinstance(content, str) or not content:
        return False
    return any(pattern.search(content) for pattern in patterns)


def filter_meta_facts(
    items: Sequence[T],
    get_content: Callable[[T], object],
    config: MetaFactFilterConfig,
) -> list[T]:
    """Drop items whose ``get_content(item)`` matches an active meta-fact pattern.

    Generic over ``T`` so callers can filter ``SearchResult`` / ``Memory`` /
    raw shapes with the same primitive. Pure and synchronous.
    """
    if not config.enabled:
        return list(items)
    patterns = resolve_meta_fact_patterns(config)
    if not patterns:
        return list(items)
    kept: list[T] = []
    for item in items:
        content = get_content(item)
        matched_index = -1
        if isinstance(content, str) and content:
            for index, pattern in enumerate(patterns):
                if pattern.search(content):
                    matched_index = index
                    break
        if matched_index >= 0:
            if config.on_drop is not None and isinstance(content, str):
                try:
                    config.on_drop(content, matched_index)
                except Exception:
                    logger.warning("meta-fact filter on_drop callback raised; ignoring", exc_info=True)
            continue
        kept.append(item)
    return kept
