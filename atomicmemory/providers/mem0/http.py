"""HTTP transport for the Mem0 provider — provider-tagged sync + async helpers.

Port of the Mem0-bound layer in `atomicmemory-sdk/src/memory/mem0-provider/http.ts`
(which itself wraps the shared `shared/http-client.ts`). Same error-mapping
policy as the AtomicMemory transport, but errors are tagged with
``provider="mem0"`` so callers can route them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from atomicmemory.core.errors import NetworkError, ProviderError, RateLimitError

_PROVIDER_NAME = "mem0"


@dataclass(frozen=True)
class HttpOptions:
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
        raise RateLimitError(
            "Rate limited",
            provider=_PROVIDER_NAME,
            retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
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
) -> httpx.Response:
    url = f"{options.api_url}{path}"
    try:
        return client.request(method, url, headers=_headers(options), json=json, timeout=options.timeout_seconds)
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


# ---- async ---------------------------------------------------------------


async def _arequest(
    client: httpx.AsyncClient,
    options: HttpOptions,
    method: str,
    path: str,
    *,
    json: Any | None = None,
) -> httpx.Response:
    url = f"{options.api_url}{path}"
    try:
        return await client.request(method, url, headers=_headers(options), json=json, timeout=options.timeout_seconds)
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
