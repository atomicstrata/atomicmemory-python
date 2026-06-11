"""Typed errors for the /v1/entities API.

Mirrors the shape of ``atomicmemory/storage/errors.py``:
every raised exception inherits from
:class:`atomicmemory.core.errors.AtomicMemoryError` and carries
``error_code``, ``status``, and ``body_text`` fields.

One deliberate divergence from storage: the non-2xx message includes
``method + path + status + body_text`` (matching the TS
``EntitiesClient:140`` style) rather than storage's path-free message.
"""

from __future__ import annotations

from typing import Any

from atomicmemory.core.errors import AtomicMemoryError


class EntitiesClientError(AtomicMemoryError):
    """Base error for ``client.entities.*`` failures."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        status: int,
        body_text: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Create an EntitiesClientError with structured metadata.

        Args:
            message: Human-readable description of the failure.
            error_code: Machine-readable error discriminant.
            status: HTTP status code (0 for non-HTTP failures).
            body_text: Raw response body text, if any.
            context: Optional extra key/value context merged into the error.
        """
        merged: dict[str, Any] = {"error_code": error_code, "status": status}
        if context:
            merged.update(context)
        super().__init__(message, context=merged)
        self.error_code = error_code
        self.status = status
        self.body_text = body_text
