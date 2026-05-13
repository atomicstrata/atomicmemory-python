"""Validation helpers shared by public SDK boundaries.

Pydantic errors can include caller input under the ``input`` key. Public
SDK exceptions should expose useful schema diagnostics without copying
API keys, metadata, or byte bodies into structured error context.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

_DROPPED_ERROR_KEYS = {"input", "ctx", "url"}


def sanitized_pydantic_errors(exc: PydanticValidationError) -> list[dict[str, Any]]:
    """Return Pydantic errors stripped of caller-supplied values."""
    sanitized: list[dict[str, Any]] = []
    for error in exc.errors():
        sanitized.append({key: value for key, value in error.items() if key not in _DROPPED_ERROR_KEYS})
    return sanitized
