"""Synchronous client for backend artifact storage.

This module calls core's `/v1/storage/artifacts/*` API and mirrors the
TypeScript SDK's `ConcreteStorageClient`. It sends bearer auth plus
``X-AtomicMemory-User-Id`` on every request and never serializes the
legacy ``?user_id=`` URL parameter.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from pydantic import ValidationError as PydanticValidationError

from atomicmemory.core.validation import sanitized_pydantic_errors
from atomicmemory.storage._mapping import (
    map_delete_result,
    map_head_headers,
    map_stored_artifact,
    map_verify_result,
    raise_for_storage_response,
    validate_response_model,
)
from atomicmemory.storage.errors import StorageClientError
from atomicmemory.storage.types import (
    ArtifactHead,
    ArtifactMetadata,
    ArtifactRef,
    DeleteArtifactOptions,
    DeleteArtifactResult,
    ManagedBody,
    PutArtifactInput,
    PutManagedInput,
    PutPointerInput,
    StorageCapabilities,
    StorageClientConfig,
    StoredArtifact,
    VerificationResult,
    VerifyArtifactOptions,
)

METADATA_HEADER = "X-AtomicMemory-Metadata"


class StorageClient:
    """Sync entry point for the direct artifact-storage API."""

    def __init__(self, config: StorageClientConfig | dict[str, Any]) -> None:
        self._config = _coerce_config(config)
        self._api_url = self._config.api_url.rstrip("/")
        self._client = httpx.Client(timeout=self._config.timeout_seconds)

    def capabilities(self) -> StorageCapabilities:
        response = self._request("GET", "/v1/storage/capabilities")
        return validate_response_model(StorageCapabilities, _json_response(response), "StorageCapabilities")

    def put(self, input: PutArtifactInput | dict[str, Any]) -> StoredArtifact:
        value = _coerce_put_input(input)
        if isinstance(value, PutPointerInput):
            return self._put_pointer(value)
        return self._put_managed(value)

    def get(self, ref: ArtifactRef | dict[str, Any]) -> StoredArtifact:
        artifact_id = _require_artifact_id(ref)
        response = self._request("GET", f"/v1/storage/artifacts/{_quote_id(artifact_id)}", artifact_id=artifact_id)
        return map_stored_artifact(_json_response(response))

    def get_content(self, ref: ArtifactRef | dict[str, Any]) -> httpx.Response:
        """Return a fully buffered content response for small artifacts.

        For large artifacts, use :meth:`stream_content` so the response
        body is consumed incrementally inside a context manager.
        """
        artifact_id = _require_artifact_id(ref)
        return self._request("GET", f"/v1/storage/artifacts/{_quote_id(artifact_id)}/content", artifact_id=artifact_id)

    @contextmanager
    def stream_content(self, ref: ArtifactRef | dict[str, Any]) -> Iterator[httpx.Response]:
        """Stream artifact bytes without loading the whole response into memory."""
        artifact_id = _require_artifact_id(ref)
        path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}/content"
        try:
            with self._client.stream("GET", f"{self._api_url}{path}", headers=self._headers(None)) as response:
                if response.is_success:
                    yield response
                    return
                response.read()
                raise_for_storage_response(response, artifact_id)
        except httpx.RequestError as exc:
            raise _network_error("GET", path, exc) from exc
        raise AssertionError("unreachable")

    def head(self, ref: ArtifactRef | dict[str, Any]) -> ArtifactHead:
        artifact_id = _require_artifact_id(ref)
        response = self._request("HEAD", f"/v1/storage/artifacts/{_quote_id(artifact_id)}", artifact_id=artifact_id)
        return map_head_headers(response.headers, artifact_id)

    def delete(
        self,
        ref: ArtifactRef | dict[str, Any],
        options: DeleteArtifactOptions | dict[str, Any] | None = None,
    ) -> DeleteArtifactResult:
        artifact_id = _require_artifact_id(ref)
        path = _delete_path(artifact_id, options)
        response = self._request("DELETE", path, artifact_id=artifact_id)
        return map_delete_result(_json_response(response))

    def verify(
        self,
        ref: ArtifactRef | dict[str, Any],
        options: VerifyArtifactOptions | dict[str, Any] | None = None,
    ) -> VerificationResult:
        _coerce_verify_options(options)
        artifact_id = _require_artifact_id(ref)
        path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}/verify"
        response = self._request("POST", path, artifact_id=artifact_id)
        return map_verify_result(_json_response(response))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StorageClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _put_pointer(self, input: PutPointerInput) -> StoredArtifact:
        payload = _pointer_payload(input)
        response = self._request(
            "POST",
            "/v1/storage/artifacts",
            headers={"Content-Type": "application/json"},
            content=json.dumps(payload, separators=(",", ":")).encode(),
        )
        return map_stored_artifact(_json_response(response))

    def _put_managed(self, input: PutManagedInput) -> StoredArtifact:
        body = _coerce_managed_body(input.body)
        path = _managed_path(input.disclose_content_hash)
        headers = {"Content-Type": input.content_type, "Content-Length": str(len(body))}
        if input.metadata is not None:
            headers[METADATA_HEADER] = _encode_metadata_header(input.metadata)
        response = self._request("POST", path, headers=headers, content=body)
        return map_stored_artifact(_json_response(response))

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        artifact_id: str | None = None,
    ) -> httpx.Response:
        try:
            response = self._client.request(
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
            "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
            "X-AtomicMemory-User-Id": self._config.user_id,
        }
        if extra:
            headers.update(extra)
        return headers


def _coerce_config(value: StorageClientConfig | dict[str, Any]) -> StorageClientConfig:
    if isinstance(value, StorageClientConfig):
        return value
    try:
        return StorageClientConfig.model_validate(value)
    except PydanticValidationError as exc:
        raise _validation_error("StorageClientConfig", exc) from exc


def _coerce_put_input(value: PutArtifactInput | dict[str, Any]) -> PutArtifactInput:
    if isinstance(value, PutPointerInput | PutManagedInput):
        return value
    if not isinstance(value, dict):
        raise _input_error("PutArtifactInput must be a model or dict")
    try:
        if value.get("mode") == "pointer":
            return PutPointerInput.model_validate(value)
        if value.get("mode") == "managed":
            return PutManagedInput.model_validate(value)
    except PydanticValidationError as exc:
        raise _validation_error("PutArtifactInput", exc) from exc
    raise _input_error("PutArtifactInput.mode must be 'pointer' or 'managed'")


def _coerce_ref(value: ArtifactRef | dict[str, Any]) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    try:
        return ArtifactRef.model_validate(value)
    except PydanticValidationError as exc:
        raise _validation_error("ArtifactRef", exc) from exc


def _coerce_delete_options(value: DeleteArtifactOptions | dict[str, Any] | None) -> DeleteArtifactOptions:
    if value is None:
        return DeleteArtifactOptions()
    if isinstance(value, DeleteArtifactOptions):
        return value
    try:
        return DeleteArtifactOptions.model_validate(value)
    except PydanticValidationError as exc:
        raise _validation_error("DeleteArtifactOptions", exc) from exc


def _coerce_verify_options(value: VerifyArtifactOptions | dict[str, Any] | None) -> VerifyArtifactOptions:
    if value is None:
        return VerifyArtifactOptions()
    if isinstance(value, VerifyArtifactOptions):
        return value
    try:
        return VerifyArtifactOptions.model_validate(value)
    except PydanticValidationError as exc:
        raise _validation_error("VerifyArtifactOptions", exc) from exc


def _require_artifact_id(ref: ArtifactRef | dict[str, Any]) -> str:
    artifact_id = _coerce_ref(ref).artifact_id
    if artifact_id is None:
        raise StorageClientError(
            "ArtifactRef.artifact_id is required for this operation in v1",
            error_code="missing_artifact_id",
            status=0,
            body_text="",
        )
    return artifact_id


def _pointer_payload(input: PutPointerInput) -> dict[str, Any]:
    payload: dict[str, Any] = {"mode": "pointer", "uri": input.uri, "content_type": input.content_type}
    if input.size_bytes is not None:
        payload["size_bytes"] = input.size_bytes
    if input.content_hash is not None:
        payload["content_hash"] = input.content_hash
    if input.metadata is not None:
        payload["metadata"] = input.metadata
    return payload


def _managed_path(disclose_content_hash: bool) -> str:
    query = {"mode": "managed"}
    if disclose_content_hash:
        query["disclose_content_hash"] = "true"
    return f"/v1/storage/artifacts?{urlencode(query)}"


def _delete_path(artifact_id: str, options: DeleteArtifactOptions | dict[str, Any] | None) -> str:
    path = f"/v1/storage/artifacts/{_quote_id(artifact_id)}"
    policy = _coerce_delete_options(options).policy
    return f"{path}?{urlencode({'policy': policy})}" if policy else path


def _coerce_managed_body(body: ManagedBody) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, bytearray):
        return bytes(body)
    if isinstance(body, memoryview):
        return body.tobytes()
    raise StorageClientError(
        "StorageClient.put: only bytes, bytearray, or memoryview are accepted in v1",
        error_code="streaming_body_not_supported",
        status=0,
        body_text="",
    )


def _encode_metadata_header(metadata: ArtifactMetadata) -> str:
    encoded = json.dumps(metadata, separators=(",", ":")).encode()
    return base64.b64encode(encoded).decode()


def _json_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise StorageClientError(
            "storage API response is not valid JSON",
            error_code="invalid_storage_response",
            status=response.status_code,
            body_text=response.text,
        ) from exc


def _quote_id(artifact_id: str) -> str:
    return quote(artifact_id, safe="")


def _validation_error(type_name: str, exc: PydanticValidationError) -> StorageClientError:
    return StorageClientError(
        f"Invalid {type_name}: {exc}",
        error_code="invalid_storage_input",
        status=0,
        body_text="",
        context={"type": type_name, "errors": sanitized_pydantic_errors(exc)},
    )


def _input_error(message: str) -> StorageClientError:
    return StorageClientError(message, error_code="invalid_storage_input", status=0, body_text="")


def _network_error(method: str, path: str, exc: httpx.RequestError) -> StorageClientError:
    return StorageClientError(
        f"Network error while calling {method} {path}: {exc}",
        error_code="network_error",
        status=0,
        body_text="",
    )
