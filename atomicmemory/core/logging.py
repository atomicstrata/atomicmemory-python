"""Logging helpers for the SDK.

Port of `atomicmemory-sdk/src/utils/logger.ts`. Wraps stdlib `logging` so
SDK callers get a consistent logger name prefix without forcing handler
configuration on the host application.
"""

from __future__ import annotations

import logging

_ROOT_LOGGER_NAME = "atomicmemory"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the ``atomicmemory`` namespace.

    Args:
        name: Optional dotted suffix appended to ``atomicmemory.``.
            ``None`` returns the root SDK logger.

    Returns:
        Configured `logging.Logger`. Handler attachment is the host
        application's responsibility; the SDK never adds default handlers.
    """
    if name is None or name == "":
        return logging.getLogger(_ROOT_LOGGER_NAME)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


def configure_logging(level: int = logging.INFO) -> None:
    """Set the SDK root logger's level.

    Useful as a one-liner during development. Production callers should
    configure their own handlers via stdlib `logging` directly.
    """
    get_logger().setLevel(level)
