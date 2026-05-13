"""Cross-cutting building blocks: errors, retry, events, logging.

Port of `atomicmemory-sdk/src/core/`. These modules are the only ones every
other layer depends on; they intentionally have no inward dependencies on
`memory/`, `providers/`, `client/`, etc.
"""

from atomicmemory.core.errors import (
    AtomicMemoryError,
    ConfigError,
    NetworkError,
    NotInitializedError,
    ProviderError,
    RateLimitError,
    ValidationError,
)
from atomicmemory.core.events import EventEmitter
from atomicmemory.core.logging import configure_logging, get_logger
from atomicmemory.core.retry import RetryConfig, with_retry

__all__ = [
    "AtomicMemoryError",
    "ConfigError",
    "EventEmitter",
    "NetworkError",
    "NotInitializedError",
    "ProviderError",
    "RateLimitError",
    "RetryConfig",
    "ValidationError",
    "configure_logging",
    "get_logger",
    "with_retry",
]
