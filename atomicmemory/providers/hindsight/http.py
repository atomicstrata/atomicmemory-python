"""HTTP transport helpers for the Hindsight provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from atomicmemory.core.errors import NetworkError, ProviderError, RateLimitError

_PROVIDER_NAME = "hindsight"


@dataclass(frozen=True)
class HttpOptions:
    api_url: str
    api_key: str | None
    timeout_seconds: float


def _headers(options: HttpOptions) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if options.api_key:
        headers["Authorization"] = f"Bearer {options.api_key}"
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
        raise RateLimitError(
            "Rate limited",
            provider=_PROVIDER_NAME,
            retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            context={"path": path},
        )
    if response.is_success:
        return
    body = _decode_body(response)
    raise ProviderError(
        f"HTTP {response.status_code}: {response.text or response.reason_phrase}",
        provider=_PROVIDER_NAME,
        status_code=response.status_code,
        response_body=body,
        context={"path": path},
    )


def _decode_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (ValueError, httpx.DecodingError):
        return response.text


def _request(
    client: httpx.Client,
    options: HttpOptions,
    method: str,
    path: str,
    *,
    json: Any | None = None,
) -> httpx.Response:
    try:
        return client.request(
            method,
            f"{options.api_url}{path}",
            headers=_headers(options),
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
    response = _request(client, options, method, path, json=json)
    _raise_for_status(response, path)
    return response.json()


def fetch_json_or_none(
    client: httpx.Client,
    options: HttpOptions,
    path: str,
    *,
    method: str = "GET",
    json: Any | None = None,
) -> Any | None:
    response = _request(client, options, method, path, json=json)
    if response.status_code == 404:
        return None
    _raise_for_status(response, path)
    return response.json()


def delete_ignore_404(client: httpx.Client, options: HttpOptions, path: str) -> None:
    response = _request(client, options, "DELETE", path)
    if response.status_code == 404:
        return
    _raise_for_status(response, path)


async def _arequest(
    client: httpx.AsyncClient,
    options: HttpOptions,
    method: str,
    path: str,
    *,
    json: Any | None = None,
) -> httpx.Response:
    try:
        return await client.request(
            method,
            f"{options.api_url}{path}",
            headers=_headers(options),
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


async def adelete_ignore_404(client: httpx.AsyncClient, options: HttpOptions, path: str) -> None:
    response = await _arequest(client, options, "DELETE", path)
    if response.status_code == 404:
        return
    _raise_for_status(response, path)
