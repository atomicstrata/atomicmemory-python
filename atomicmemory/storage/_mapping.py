"""Wire mappers for backend artifact-storage responses.

Core emits snake_case JSON and storage HEAD headers. This module is the
single translation seam into Python SDK models, with closed-enum
validation before any public model is returned.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from atomicmemory.storage.errors import (
    ArtifactInUseError,
    ArtifactNotFoundError,
    FilecoinDirectStorageNotSupportedError,
    PointerContentNotManagedError,
    StorageClientError,
    UnsupportedCapabilityError,
)
from atomicmemory.storage.types import (
    ArtifactHead,
    DeleteArtifactResult,
    StorageArtifactStatus,
    StoredArtifact,
    VerificationResult,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

STORAGE_MODES = ("pointer", "managed")
STORAGE_STATUSES: tuple[StorageArtifactStatus, ...] = (
    "stored",
    "pending",
    "available",
    "unavailable",
    "deleting",
    "deleted",
    "delete_failed",
    "failed",
)
CONTENT_ENCODINGS = ("identity", "aes_gcm")


def map_stored_artifact(raw: Any) -> StoredArtifact:
    """Translate and validate a snake_case artifact response."""
    body = _require_object(raw, "StoredArtifact")
    artifact_id = _require_wire_string(body, "artifact_id")
    provider = _require_wire_string(body, "provider")
    mode = _require_wire_enum(body, "mode", STORAGE_MODES)
    status = _require_wire_enum(body, "status", STORAGE_STATUSES)
    content_encoding = _require_wire_enum(body, "content_encoding", CONTENT_ENCODINGS)
    artifact = {
        "artifactId": artifact_id,
        "provider": provider,
        "mode": mode,
        "uri": _optional_string(body, "uri"),
        "status": status,
        "sizeBytes": _optional_non_negative_int(body, "size_bytes"),
        "contentType": _optional_string(body, "content_type"),
        "contentEncoding": content_encoding,
        "identifiers": _string_dict(body, "identifiers"),
        "lifecycle": _object_or_empty(body, "lifecycle"),
        "metadata": _metadata_dict(body, "metadata"),
        "createdAt": _require_wire_string(body, "created_at"),
        "updatedAt": _require_wire_string(body, "updated_at"),
    }
    content_hash = _optional_string(body, "content_hash")
    if content_hash is not None:
        artifact["contentHash"] = content_hash
    _copy_optional_object(artifact, "providerDetails", body, "provider_details")
    _copy_optional_object(artifact, "replication", body, "replication")
    _copy_optional_object(artifact, "verification", body, "verification")
    _copy_optional_object(artifact, "retrieval", body, "retrieval")
    return validate_response_model(StoredArtifact, artifact, "StoredArtifact")


def map_head_headers(headers: httpx.Headers, fallback_id: str) -> ArtifactHead:
    """Project storage HEAD response headers into an ``ArtifactHead``."""
    mode = _validate_header_enum(headers, "x-atomicmemory-storage-mode", STORAGE_MODES)
    status = _validate_header_enum(headers, "x-atomicmemory-storage-status", STORAGE_STATUSES)
    return validate_response_model(
        ArtifactHead,
        {
            "artifactId": headers.get("x-atomicmemory-artifact-id") or fallback_id,
            "provider": headers.get("x-atomicmemory-provider") or "",
            "mode": mode,
            "status": status,
            "sizeBytes": _parse_size(headers.get("content-length")),
            "contentType": headers.get("content-type"),
        },
        "ArtifactHead",
    )


def map_delete_result(raw: Any) -> DeleteArtifactResult:
    """Translate and validate a snake_case delete response."""
    body = _require_object(raw, "DeleteArtifactResult")
    out: dict[str, Any] = {
        "artifactId": _require_wire_string(body, "artifact_id"),
        "status": _require_wire_enum(body, "status", STORAGE_STATUSES),
    }
    if isinstance(body.get("cascaded_document_ids"), list):
        out["cascadedDocumentIds"] = [str(v) for v in body["cascaded_document_ids"]]
    return validate_response_model(DeleteArtifactResult, out, "DeleteArtifactResult")


def map_verify_result(raw: Any) -> VerificationResult:
    """Map verification response variants to a single Python model."""
    body = raw if isinstance(raw, dict) else {}
    if body.get("kind") == "verified":
        details = body.get("details") if isinstance(body.get("details"), dict) else {}
        return validate_response_model(
            VerificationResult, {"kind": "verified", "details": details}, "VerificationResult"
        )
    if body.get("kind") == "failed":
        failed = {"kind": "failed", "reason": str(body.get("reason", "unknown failure"))}
        return validate_response_model(VerificationResult, failed, "VerificationResult")
    unsupported = {"kind": "unsupported", "reason": str(body.get("reason", "unsupported"))}
    return validate_response_model(VerificationResult, unsupported, "VerificationResult")


def validate_response_model(model: type[ModelT], data: dict[str, Any], type_name: str) -> ModelT:
    """Validate a response model without leaking Pydantic errors."""
    try:
        return model.model_validate(data)
    except PydanticValidationError as exc:
        raise StorageClientError(
            f"{type_name}: server response failed validation",
            error_code="invalid_storage_response",
            status=200,
            body_text="",
            context={"type": type_name, "errors": exc.errors()},
        ) from exc


def raise_for_storage_response(response: httpx.Response, artifact_id: str | None = None) -> None:
    """Raise the typed storage error for a non-success response."""
    body_text = response.text
    envelope = _parse_error_envelope(body_text)
    code = envelope.get("error_code")
    message = str(envelope.get("error") or f"request failed with status {response.status_code}")
    known_id = artifact_id or ""
    if code == "artifact_in_use":
        count = envelope.get("referenced_by_document_count")
        raise ArtifactInUseError(
            artifact_id=known_id,
            referenced_by_document_count=count if isinstance(count, int) else 0,
            body_text=body_text,
        )
    if code == "pointer_content_not_managed":
        uri = envelope.get("uri")
        raise PointerContentNotManagedError(
            artifact_id=known_id,
            uri=uri if isinstance(uri, str) else "",
            body_text=body_text,
        )
    if code == "filecoin_direct_storage_not_yet_supported":
        raise FilecoinDirectStorageNotSupportedError(body_text=body_text)
    if code == "artifact_not_found" or response.status_code == 404:
        raise ArtifactNotFoundError(artifact_id=known_id, body_text=body_text)
    if code == "unsupported_capability":
        raise UnsupportedCapabilityError(capability="unknown", message=message, body_text=body_text)
    raise StorageClientError(
        message,
        error_code=code if isinstance(code, str) else f"http_{response.status_code}",
        status=response.status_code,
        body_text=body_text,
    )


def _require_object(raw: Any, type_name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StorageClientError(
            f"{type_name}: server response is not a JSON object",
            error_code="invalid_storage_response",
            status=200,
            body_text="",
        )
    return raw


def _require_wire_string(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or value == "":
        raise StorageClientError(
            f"mapStoredArtifact: server response is missing required `{field}`",
            error_code="invalid_storage_response",
            status=200,
            body_text="",
        )
    return str(value)


def _require_wire_enum(raw: dict[str, Any], field: str, allowed: Iterable[str]) -> str:
    value = raw.get(field)
    allowed_values = tuple(allowed)
    if not isinstance(value, str) or value not in allowed_values:
        raise StorageClientError(
            f"mapStoredArtifact: `{field}` must be one of {', '.join(allowed_values)}",
            error_code="invalid_storage_response",
            status=200,
            body_text="",
        )
    return value


def _validate_header_enum(headers: httpx.Headers, name: str, allowed: Iterable[str]) -> str:
    value = headers.get(name)
    allowed_values = tuple(allowed)
    if not isinstance(value, str) or value not in allowed_values:
        raise StorageClientError(
            f"head(): server returned an unrecognized {name} value",
            error_code="invalid_head_response",
            status=200,
            body_text="",
        )
    return value


def _parse_size(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _optional_string(body: dict[str, Any], field: str) -> str | None:
    if field not in body or body[field] is None:
        return None
    value = body[field]
    if isinstance(value, str):
        return value
    raise _invalid_response(f"mapStoredArtifact: `{field}` must be a string or null")


def _optional_non_negative_int(body: dict[str, Any], field: str) -> int | None:
    if field not in body or body[field] is None:
        return None
    value = body[field]
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    raise _invalid_response(f"mapStoredArtifact: `{field}` must be a non-negative integer or null")


def _string_dict(body: dict[str, Any], field: str) -> dict[str, str]:
    if field not in body or body[field] is None:
        return {}
    value = body[field]
    if not isinstance(value, dict):
        raise _invalid_response(f"mapStoredArtifact: `{field}` must be an object")
    if not all(isinstance(v, str) for v in value.values()):
        raise _invalid_response(f"mapStoredArtifact: `{field}` values must be strings")
    return {str(k): v for k, v in value.items()}


def _object_or_empty(body: dict[str, Any], field: str) -> dict[str, Any]:
    if field not in body or body[field] is None:
        return {}
    value = body[field]
    if not isinstance(value, dict):
        raise _invalid_response(f"mapStoredArtifact: `{field}` must be an object")
    return value


def _metadata_dict(body: dict[str, Any], field: str) -> dict[str, str | int | float | bool]:
    if field not in body or body[field] is None:
        return {}
    value = body[field]
    if not isinstance(value, dict):
        raise _invalid_response(f"mapStoredArtifact: `{field}` must be an object")
    if not all(isinstance(v, str | int | float | bool) for v in value.values()):
        raise _invalid_response(f"mapStoredArtifact: `{field}` values must be scalar")
    return {str(k): v for k, v in value.items() if isinstance(v, str | int | float | bool)}


def _copy_optional_object(out: dict[str, Any], out_key: str, body: dict[str, Any], wire_key: str) -> None:
    if wire_key not in body or body[wire_key] is None:
        return
    value = body[wire_key]
    if not isinstance(value, dict):
        raise _invalid_response(f"mapStoredArtifact: `{wire_key}` must be an object")
    out[out_key] = value


def _invalid_response(message: str) -> StorageClientError:
    return StorageClientError(message, error_code="invalid_storage_response", status=200, body_text="")


def _parse_error_envelope(body_text: str) -> dict[str, Any]:
    if body_text == "":
        return {}
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
