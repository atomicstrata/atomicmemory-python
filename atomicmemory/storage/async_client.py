"""Async client for backend artifact storage.

The async surface mirrors :mod:`atomicmemory.storage.client` while
using ``httpx.AsyncClient`` for every storage API request.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any

import httpx

from atomicmemory.storage._mapping import (
    map_delete_result,
    map_head_headers,
    map_stored_artifact,
    map_verify_result,
    raise_for_storage_response,
    validate_response_model,
)
from atomicmemory.storage.client import (
    METADATA_HEADER,
    _coerce_config,
    _coerce_delete_options,
    _coerce_managed_body,
    _coerce_put_input,
    _coerce_verify_options,
    _encode_metadata_header,
    _json_response,
    _managed_path,
    _network_error,
    _pointer_payload,
    _quote_id,
    _require_artifact_id,
)
from atomicmemory.storage.types import (
    ArtifactHead,
    ArtifactRef,
    DeleteArtifactOptions,
    DeleteArtifactResult,
    PutArtifactInput,
    PutManagedInput,
    PutPointerInput,
    StorageCapabilities,
    StorageClientConfig,
    StoredArtifact,
    VerificationResult,
    VerifyArtifactOptions,
)


class AsyncStorageClient:
    """Async entry point for the direct artifact-storage API."""

    def __init__(self, config: StorageClientConfig | dict[str, Any]) -> None:
        self._config = _coerce_config(config)
        self._api_url = self._config.api_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=self._config.timeout_seconds)

    async def capabilities(self) -> StorageCapabilities:
        response = await self._request("GET", "/v1/storage/capabilities")
        return validate_response_model(StorageCapabilities, _json_response(response), "StorageCapabilities")

    async def put(self, input: PutArtifactInput | dict[str, Any]) -> StoredArtifact:
        value = _coerce_put_input(input)
        if isinstance(value, PutPointerInput):
            return await self._put_pointer(value)
        return await self._put_managed(value)

    async def get(self, ref: ArtifactRef | dict[str, Any]) -> StoredArtifact:
        artifact_id = _require_artifact_id(ref)
        response = await self._request(
            "GET",
            f"/v1/storage/artifacts/{_quote_id(artifact_id)}",
            artifact_id=artifact_id,
        )
        return map_stored_artifact(_json_response(response))

    async def get_content(self, ref: ArtifactRef | dict[str, Any]) -> httpx.Response:
        """Return a fully buffered content response for small artifacts."""
        artifact_id = _require_artifact_id(ref)
        path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}/content"
        return await self._request("GET", path, artifact_id=artifact_id)

    @asynccontextmanager
    async def stream_content(self, ref: ArtifactRef | dict[str, Any]) -> AsyncIterator[httpx.Response]:
        """Stream artifact bytes without loading the whole response into memory."""
        artifact_id = _require_artifact_id(ref)
        path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}/content"
        try:
            async with self._client.stream("GET", f"{self._api_url}{path}", headers=self._headers(None)) as response:
                if response.is_success:
                    yield response
                    return
                await response.aread()
                raise_for_storage_response(response, artifact_id)
        except httpx.RequestError as exc:
            raise _network_error("GET", path, exc) from exc
        raise AssertionError("unreachable")

    async def head(self, ref: ArtifactRef | dict[str, Any]) -> ArtifactHead:
        artifact_id = _require_artifact_id(ref)
        response = await self._request(
            "HEAD",
            f"/v1/storage/artifacts/{_quote_id(artifact_id)}",
            artifact_id=artifact_id,
        )
        return map_head_headers(response.headers, artifact_id)

    async def delete(
        self,
        ref: ArtifactRef | dict[str, Any],
        options: DeleteArtifactOptions | dict[str, Any] | None = None,
    ) -> DeleteArtifactResult:
        artifact_id = _require_artifact_id(ref)
        path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}"
        policy = _coerce_delete_options(options).policy
        if policy:
            path = f"{path}?policy={policy}"
        response = await self._request("DELETE", path, artifact_id=artifact_id)
        return map_delete_result(_json_response(response))

    async def verify(
        self,
        ref: ArtifactRef | dict[str, Any],
        options: VerifyArtifactOptions | dict[str, Any] | None = None,
    ) -> VerificationResult:
        _coerce_verify_options(options)
        artifact_id = _require_artifact_id(ref)
        path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}/verify"
        response = await self._request("POST", path, artifact_id=artifact_id)
        return map_verify_result(_json_response(response))

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncStorageClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def _put_pointer(self, input: PutPointerInput) -> StoredArtifact:
        response = await self._request(
            "POST",
            "/v1/storage/artifacts",
            headers={"Content-Type": "application/json"},
            content=_json_bytes(_pointer_payload(input)),
        )
        return map_stored_artifact(_json_response(response))

    async def _put_managed(self, input: PutManagedInput) -> StoredArtifact:
        body = _coerce_managed_body(input.body)
        headers = {"Content-Type": input.content_type, "Content-Length": str(len(body))}
        if input.metadata is not None:
            headers[METADATA_HEADER] = _encode_metadata_header(input.metadata)
        response = await self._request(
            "POST",
            _managed_path(input.disclose_content_hash),
            headers=headers,
            content=body,
        )
        return map_stored_artifact(_json_response(response))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        artifact_id: str | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method,
                f"{self._api_url}{path}",
                headers=self._headers(headers),
                content=content,
            )
        except httpx.RequestError as exc:
            raise _network_error(method, path, exc) from exc
        if response.is_success:
            return response
        raise_for_storage_response(response, artifact_id)
        raise AssertionError("unreachable")

    def _headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "X-AtomicMemory-User-Id": self._config.user_id,
        }
        if extra:
            headers.update(extra)
        return headers


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()
