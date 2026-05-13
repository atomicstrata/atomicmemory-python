"""Tests for atomicmemory.core.errors."""

from __future__ import annotations

import pytest

from atomicmemory.core.errors import (
    AtomicMemoryError,
    ConfigError,
    NetworkError,
    NotInitializedError,
    ProviderError,
    ValidationError,
)


def test_base_error_carries_message_and_context() -> None:
    err = AtomicMemoryError("something broke", context={"route": "/x", "attempt": 2})

    assert err.message == "something broke"
    assert err.context == {"route": "/x", "attempt": 2}
    assert str(err) == "something broke"


def test_subclasses_inherit_from_base() -> None:
    for cls in (ConfigError, ValidationError, NotInitializedError):
        instance = cls("x")
        assert isinstance(instance, AtomicMemoryError)


def test_provider_error_attaches_provider_metadata() -> None:
    err = ProviderError(
        "boom",
        provider="atomicmemory",
        status_code=502,
        response_body={"error": "upstream"},
    )

    assert err.provider == "atomicmemory"
    assert err.status_code == 502
    assert err.response_body == {"error": "upstream"}
    assert err.context["provider"] == "atomicmemory"
    assert err.context["status_code"] == 502


def test_network_error_chains_cause() -> None:
    cause = TimeoutError("dns lookup failed")
    err = NetworkError("transport failed", provider="atomicmemory", cause=cause)

    assert err.provider == "atomicmemory"
    assert err.__cause__ is cause


def test_provider_error_is_raisable_and_catchable_as_base() -> None:
    with pytest.raises(AtomicMemoryError) as excinfo:
        raise ProviderError("denied", provider="mem0", status_code=403)

    assert isinstance(excinfo.value, ProviderError)
    assert excinfo.value.status_code == 403
