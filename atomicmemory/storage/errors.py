"""Typed errors for the backend artifact-storage API.

These classes mirror `atomicmemory-sdk/src/storage/errors.ts` while
following the Python SDK error contract: every SDK-raised exception
inherits from :class:`atomicmemory.core.errors.AtomicMemoryError`.
"""

from __future__ import annotations

from typing import Any

from atomicmemory.core.errors import AtomicMemoryError


class StorageClientError(AtomicMemoryError):
    """Base error for ``client.storage.*`` failures."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        status: int,
        body_text: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged = {"error_code": error_code, "status": status}
        if context:
            merged.update(context)
        super().__init__(message, context=merged)
        self.error_code = error_code
        self.status = status
        self.body_text = body_text


class UnsupportedCapabilityError(StorageClientError):
    """A requested storage capability is not supported by the backend."""

    def __init__(self, *, capability: str, message: str, body_text: str) -> None:
        super().__init__(
            message,
            error_code="unsupported_capability",
            status=400,
            body_text=body_text,
            context={"capability": capability},
        )
        self.capability = capability


class ArtifactNotFoundError(StorageClientError):
    """The requested artifact does not exist for the caller."""

    def __init__(self, *, artifact_id: str, body_text: str) -> None:
        super().__init__(
            f"Storage artifact {artifact_id} not found",
            error_code="artifact_not_found",
            status=404,
            body_text=body_text,
            context={"artifact_id": artifact_id},
        )
        self.artifact_id = artifact_id


class ArtifactInUseError(StorageClientError):
    """The artifact is still referenced by one or more documents."""

    def __init__(
        self,
        *,
        artifact_id: str,
        referenced_by_document_count: int,
        body_text: str,
    ) -> None:
        super().__init__(
            "Storage artifact "
            f"{artifact_id} is referenced by {referenced_by_document_count} document(s); "
            "pass policy='with_documents' to cascade",
            error_code="artifact_in_use",
            status=409,
            body_text=body_text,
            context={
                "artifact_id": artifact_id,
                "referenced_by_document_count": referenced_by_document_count,
            },
        )
        self.artifact_id = artifact_id
        self.referenced_by_document_count = referenced_by_document_count


class PointerContentNotManagedError(StorageClientError):
    """Raised when ``get_content`` targets a pointer-mode artifact."""

    def __init__(self, *, artifact_id: str, uri: str, body_text: str) -> None:
        super().__init__(
            f"Artifact {artifact_id} is pointer-mode; fetch the URI directly",
            error_code="pointer_content_not_managed",
            status=409,
            body_text=body_text,
            context={"artifact_id": artifact_id, "uri": uri},
        )
        self.artifact_id = artifact_id
        self.uri = uri


class FilecoinDirectStorageNotSupportedError(StorageClientError):
    """Direct managed Filecoin uploads are not supported by this API version."""

    def __init__(self, *, body_text: str) -> None:
        super().__init__(
            "Direct Filecoin artifact uploads are not supported in this version. "
            "Use document ingestion or pointer mode.",
            error_code="filecoin_direct_storage_not_yet_supported",
            status=501,
            body_text=body_text,
        )
