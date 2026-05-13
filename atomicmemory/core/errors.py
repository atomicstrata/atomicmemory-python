"""Error hierarchy for the atomicmemory SDK.

Port of `atomicmemory-sdk/src/core/error-handling/`. Every SDK-raised
exception inherits from `AtomicMemoryError` so callers can catch the
whole surface with one type.
"""

from __future__ import annotations

from typing import Any


class AtomicMemoryError(Exception):
    """Base class for every error raised by this SDK.

    Attributes:
        message: Human-readable description.
        context: Free-form structured data (e.g. provider name, route,
            request body fingerprint) that aids debugging without leaking
            secrets.
    """

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context) if context else {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r}, context={self.context!r})"


class ConfigError(AtomicMemoryError):
    """Configuration is missing, malformed, or self-inconsistent."""


class ValidationError(AtomicMemoryError):
    """Input failed schema or invariant validation before any I/O."""


class NotInitializedError(AtomicMemoryError):
    """A client method was called before `initialize()` completed."""


class ProviderError(AtomicMemoryError):
    """A backing provider returned an error or the request was rejected.

    Wraps backend HTTP errors. `status_code` and `response_body` are
    populated when the underlying transport surfaced them.

    Attributes:
        provider: Provider name, e.g. ``"atomicmemory"`` or ``"mem0"``.
        status_code: HTTP status code if the failure originated from a
            response; ``None`` for transport-level failures (use
            `NetworkError` for those).
        response_body: Decoded response body when available.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        response_body: Any | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {"provider": provider}
        if status_code is not None:
            merged["status_code"] = status_code
        if context:
            merged.update(context)
        super().__init__(message, context=merged)
        self.provider = provider
        self.status_code = status_code
        self.response_body = response_body


class NetworkError(AtomicMemoryError):
    """A transport-level failure (timeout, connection refused, DNS, etc.)."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        cause: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {"provider": provider}
        if context:
            merged.update(context)
        super().__init__(message, context=merged)
        self.provider = provider
        self.__cause__ = cause


class RateLimitError(ProviderError):
    """The backend returned HTTP 429 (rate limited).

    `retry_after_seconds` is populated when the response carried a
    `Retry-After` header (in seconds). Callers may use it to drive a
    deferred retry.
    """

    def __init__(
        self,
        message: str = "Rate limited",
        *,
        provider: str,
        retry_after_seconds: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = dict(context) if context else {}
        if retry_after_seconds is not None:
            merged["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message,
            provider=provider,
            status_code=429,
            context=merged,
        )
        self.retry_after_seconds = retry_after_seconds
