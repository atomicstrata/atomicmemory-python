"""Sync HTTP transport for the AtomicMemory provider.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/http.ts` and
the shared client at `atomicmemory-sdk/src/memory/shared/http-client.ts`.

This module owns the wire-error mapping policy:

- 429 → ``RateLimitError`` (with optional ``Retry-After`` seconds).
- non-2xx → ``ProviderError`` with ``status_code`` and decoded body.
- transport failure (timeout, DNS, connection) → ``NetworkError``.
- 404 is special-cased on ``fetch_json_or_none`` and ``delete_ignore_404``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from atomicmemory.core.errors import NetworkError, ProviderError, RateLimitError

_PROVIDER_NAME = "atomicmemory"


@dataclass(frozen=True)
class HttpOptions:
    """Per-request transport options, derived from provider config."""

    api_url: str
    api_key: str | None
    timeout_seconds: float


def _headers(options: HttpOptions, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if options.api_key:
        headers["Authorization"] = f"Bearer {options.api_key}"
    if extra:
        headers.update(extra)
    return headers


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _raise_for_status(response: httpx.Response, path: str) -> None:
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise RateLimitError(
            "Rate limited",
            provider=_PROVIDER_NAME,
            retry_after_seconds=retry_after,
            context={"path": path},
        )
    if response.is_success:
        return
    body_text = response.text
    body_decoded: Any = body_text
    try:
        body_decoded = response.json()
    except (ValueError, httpx.DecodingError):
        body_decoded = body_text
    raise ProviderError(
        f"HTTP {response.status_code}: {body_text or response.reason_phrase}",
        provider=_PROVIDER_NAME,
        status_code=response.status_code,
        response_body=body_decoded,
        context={"path": path},
    )


def _request(
    client: httpx.Client,
    options: HttpOptions,
    method: str,
    path: str,
    *,
    json: Any | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    url = f"{options.api_url}{path}"
    try:
        return client.request(
            method,
            url,
            headers=_headers(options, headers),
            json=json,
            timeout=options.timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise NetworkError(
            f"Timeout after {options.timeout_seconds}s",
            provider=_PROVIDER_NAME,
            cause=exc,
            context={"path": path, "method": method},
        ) from exc
    except httpx.RequestError as exc:
        raise NetworkError(
            f"Transport error: {exc}",
            provider=_PROVIDER_NAME,
            cause=exc,
            context={"path": path, "method": method},
        ) from exc


def fetch_json(
    client: httpx.Client,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> Any:
    """Send a request and return the decoded JSON response body."""
    response = _request(client, options, method, path, json=json)
    _raise_for_status(response, path)
    return response.json()


def fetch_void(
    client: httpx.Client,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> None:
    """Send a request and discard the body."""
    response = _request(client, options, method, path, json=json)
    _raise_for_status(response, path)


def fetch_json_or_none(
    client: httpx.Client,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> Any | None:
    """Send a request; return None on 404, decoded JSON otherwise."""
    response = _request(client, options, method, path, json=json)
    if response.status_code == 404:
        return None
    _raise_for_status(response, path)
    return response.json()


def delete_ignore_404(
    client: httpx.Client,
    options: HttpOptions,
    path: str,
) -> None:
    """DELETE that swallows 404 (V3 contract: missing target = success)."""
    response = _request(client, options, "DELETE", path)
    if response.status_code == 404:
        return
    _raise_for_status(response, path)


# ---------------------------------------------------------------------------
# Async transport — paired with the sync helpers above.
# ---------------------------------------------------------------------------


async def _arequest(
    client: httpx.AsyncClient,
    options: HttpOptions,
    method: str,
    path: str,
    *,
    json: Any | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    url = f"{options.api_url}{path}"
    try:
        return await client.request(
            method,
            url,
            headers=_headers(options, headers),
            json=json,
            timeout=options.timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise NetworkError(
            f"Timeout after {options.timeout_seconds}s",
            provider=_PROVIDER_NAME,
            cause=exc,
            context={"path": path, "method": method},
        ) from exc
    except httpx.RequestError as exc:
        raise NetworkError(
            f"Transport error: {exc}",
            provider=_PROVIDER_NAME,
            cause=exc,
            context={"path": path, "method": method},
        ) from exc


async def afetch_json(
    client: httpx.AsyncClient,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> Any:
    response = await _arequest(client, options, method, path, json=json)
    _raise_for_status(response, path)
    return response.json()


async def afetch_void(
    client: httpx.AsyncClient,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> None:
    response = await _arequest(client, options, method, path, json=json)
    _raise_for_status(response, path)


async def afetch_json_or_none(
    client: httpx.AsyncClient,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> Any | None:
    response = await _arequest(client, options, method, path, json=json)
    if response.status_code == 404:
        return None
    _raise_for_status(response, path)
    return response.json()


async def adelete_ignore_404(
    client: httpx.AsyncClient,
    options: HttpOptions,
    path: str,
) -> None:
    response = await _arequest(client, options, "DELETE", path)
    if response.status_code == 404:
        return
    _raise_for_status(response, path)
