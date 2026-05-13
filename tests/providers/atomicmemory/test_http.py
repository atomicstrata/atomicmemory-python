"""Tests for the sync HTTP transport (httpx + respx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from atomicmemory.core.errors import NetworkError, ProviderError, RateLimitError
from atomicmemory.providers.atomicmemory.http import (
    HttpOptions,
    delete_ignore_404,
    fetch_json,
    fetch_json_or_none,
)

_OPTS = HttpOptions(api_url="http://core.test", api_key="secret-token", timeout_seconds=5.0)


@respx.mock
def test_fetch_json_attaches_bearer_auth_and_returns_decoded_body() -> None:
    route = respx.get("http://core.test/v1/x").mock(
        return_value=httpx.Response(200, json={"ok": True}),
    )
    with httpx.Client() as client:
        result = fetch_json(client, _OPTS, "/v1/x")

    assert result == {"ok": True}
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer secret-token"
    assert sent.headers["Content-Type"] == "application/json"


@respx.mock
def test_fetch_json_raises_provider_error_on_4xx_with_body() -> None:
    respx.post("http://core.test/v1/fail").mock(
        return_value=httpx.Response(400, json={"error": "bad request"}),
    )
    with httpx.Client() as client, pytest.raises(ProviderError) as excinfo:
        fetch_json(client, _OPTS, "/v1/fail", method="POST", json={})

    assert excinfo.value.status_code == 400
    assert excinfo.value.response_body == {"error": "bad request"}


@respx.mock
def test_fetch_json_raises_rate_limit_with_retry_after() -> None:
    respx.get("http://core.test/v1/x").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "12"}),
    )
    with httpx.Client() as client, pytest.raises(RateLimitError) as excinfo:
        fetch_json(client, _OPTS, "/v1/x")

    assert excinfo.value.retry_after_seconds == 12.0


@respx.mock
def test_fetch_json_or_none_returns_none_on_404() -> None:
    respx.get("http://core.test/v1/missing").mock(return_value=httpx.Response(404))
    with httpx.Client() as client:
        assert fetch_json_or_none(client, _OPTS, "/v1/missing") is None


@respx.mock
def test_delete_ignore_404_swallows_404() -> None:
    respx.delete("http://core.test/v1/missing").mock(return_value=httpx.Response(404))
    with httpx.Client() as client:
        delete_ignore_404(client, _OPTS, "/v1/missing")


@respx.mock
def test_delete_ignore_404_raises_on_other_errors() -> None:
    respx.delete("http://core.test/v1/oops").mock(return_value=httpx.Response(500, json={}))
    with httpx.Client() as client, pytest.raises(ProviderError):
        delete_ignore_404(client, _OPTS, "/v1/oops")


@respx.mock
def test_fetch_json_wraps_transport_errors_in_network_error() -> None:
    respx.get("http://core.test/v1/x").mock(side_effect=httpx.ConnectError("boom"))
    with httpx.Client() as client, pytest.raises(NetworkError) as excinfo:
        fetch_json(client, _OPTS, "/v1/x")

    assert excinfo.value.provider == "atomicmemory"
