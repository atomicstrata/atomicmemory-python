"""Types for the backend artifact-storage API.

Port of `atomicmemory-sdk/src/storage/types.ts`. Python callers use
snake_case field names while Pydantic aliases accept the TypeScript
SDK's camelCase spellings at the public boundary.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

StorageArtifactStatus = Literal[
    "stored",
    "pending",
    "available",
    "unavailable",
    "deleting",
    "deleted",
    "delete_failed",
    "failed",
]
StorageAddressingMode = Literal["location", "content", "provider_native"]
StorageConsistency = Literal["immediate", "eventual"]
StorageAvailabilityModel = Literal["immediate", "delayed", "scheduled", "best_effort"]
StorageDeleteSemantics = Literal["delete", "unpin", "tombstone", "provider_retained"]
StorageMode = Literal["pointer", "managed"]
ContentEncoding = Literal["identity", "aes_gcm"]
DeleteArtifactPolicy = Literal["artifact_only", "with_documents"]
ArtifactMetadata = dict[str, str | int | float | bool]
ManagedBody = bytes | bytearray | memoryview


class StorageClientConfig(BaseModel):
    """Configuration for sync and async storage clients."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_url: str = Field(alias="apiUrl")
    api_key: SecretStr = Field(alias="apiKey")
    user_id: str = Field(alias="userId")
    timeout_seconds: float = Field(default=30.0, alias="timeoutSeconds")

    @field_validator("api_url")
    @classmethod
    def _validate_api_url(cls, value: str) -> str:
        stripped = value.strip()
        parsed = urlparse(stripped)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("api_url must be an http(s) URL")
        return stripped

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: object) -> object:
        # Validate before SecretStr wraps the value so we can call .strip().
        if isinstance(value, str) and value.strip() == "":
            raise ValueError("value must not be empty")
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("user_id")
    @classmethod
    def _validate_user_id(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value

    @model_validator(mode="after")
    def _require_non_empty(self) -> StorageClientConfig:
        if not self.api_url:
            raise ValueError("api_url is required")
        # api_key is always truthy as SecretStr; empty string rejected by _validate_api_key above.
        if not self.user_id:
            raise ValueError("user_id is required")
        return self


class ArtifactRef(BaseModel):
    """Stable reference to a storage artifact.

    At least one identifier is required. v1 follow-up operations use
    ``artifact_id`` as the canonical handle.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str | None = Field(default=None, alias="artifactId")
    uri: str | None = None
    content_hash: str | None = Field(default=None, alias="contentHash")

    @model_validator(mode="after")
    def _require_one_identifier(self) -> ArtifactRef:
        if self.artifact_id is None and self.uri is None and self.content_hash is None:
            raise ValueError("ArtifactRef requires artifact_id, uri, or content_hash")
        return self


class StorageLifecycle(BaseModel):
    """Provider-agnostic availability and delete-semantics summary."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    availability: StorageAvailabilityModel | None = None
    delete_semantics: StorageDeleteSemantics | None = Field(default=None, alias="deleteSemantics")


class ReplicationState(BaseModel):
    """Optional replication state for backends such as Filecoin."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    desired_copies: int | None = Field(default=None, alias="desiredCopies")
    confirmed_copies: int | None = Field(default=None, alias="confirmedCopies")


class VerificationState(BaseModel):
    """Optional provider-proof or content-verification state."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider_proof_status: Literal["pending", "verified", "failed", "unsupported"] | None = Field(
        default=None,
        alias="providerProofStatus",
    )
    last_verified_at: str | None = Field(default=None, alias="lastVerifiedAt")


class RetrievalState(BaseModel):
    """Optional retrieval-readiness state."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: Literal["not_checked", "retrievable", "not_retrievable", "unsupported"] | None = None
    last_checked_at: str | None = Field(default=None, alias="lastCheckedAt")


class StoredArtifact(BaseModel):
    """Artifact metadata returned by ``storage.put`` and ``storage.get``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str = Field(alias="artifactId")
    provider: str
    mode: StorageMode
    uri: str | None
    status: StorageArtifactStatus
    size_bytes: int | None = Field(alias="sizeBytes")
    content_type: str | None = Field(alias="contentType")
    content_hash: str | None = Field(default=None, alias="contentHash")
    content_encoding: ContentEncoding = Field(alias="contentEncoding")
    identifiers: dict[str, str] = Field(default_factory=dict)
    lifecycle: StorageLifecycle = Field(default_factory=StorageLifecycle)
    replication: ReplicationState | None = None
    verification: VerificationState | None = None
    retrieval: RetrievalState | None = None
    provider_details: dict[str, Any] | None = Field(default=None, alias="providerDetails")
    metadata: ArtifactMetadata = Field(default_factory=dict)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class ArtifactRange(BaseModel):
    """Byte range for future range-read capable storage backends."""

    model_config = ConfigDict(extra="forbid")

    start: int
    end: int

    @model_validator(mode="after")
    def _validate_range(self) -> ArtifactRange:
        if self.start < 0:
            raise ValueError("start must be non-negative")
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class PutPointerInput(BaseModel):
    """Pointer-mode put input. The server stores metadata only."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["pointer"] = "pointer"
    uri: str
    content_type: str = Field(alias="contentType")
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    content_hash: str | None = Field(default=None, alias="contentHash")
    metadata: ArtifactMetadata | None = None

    @field_validator("content_type")
    @classmethod
    def _validate_content_type(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise ValueError("content_type must not be empty")
        return stripped


class PutManagedInput(BaseModel):
    """Managed-mode put input for known-length byte bodies."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, arbitrary_types_allowed=True)

    mode: Literal["managed"] = "managed"
    body: ManagedBody
    content_type: str = Field(alias="contentType")
    disclose_content_hash: bool = Field(default=False, alias="discloseContentHash")
    metadata: ArtifactMetadata | None = None

    @field_validator("body", mode="before")
    @classmethod
    def _validate_body(cls, value: Any) -> Any:
        if isinstance(value, bytes | bytearray | memoryview):
            return value
        raise ValueError("body must be bytes, bytearray, or memoryview")

    @field_validator("content_type")
    @classmethod
    def _validate_content_type(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise ValueError("content_type must not be empty")
        return stripped


PutArtifactInput = PutPointerInput | PutManagedInput


class ArtifactHead(BaseModel):
    """Metadata projection returned by ``storage.head``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str = Field(alias="artifactId")
    provider: str
    mode: StorageMode
    status: StorageArtifactStatus
    size_bytes: int | None = Field(alias="sizeBytes")
    content_type: str | None = Field(alias="contentType")


class DeleteArtifactOptions(BaseModel):
    """Options for ``storage.delete``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    policy: DeleteArtifactPolicy | None = None


class DeleteArtifactResult(BaseModel):
    """Result returned by ``storage.delete``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str = Field(alias="artifactId")
    status: StorageArtifactStatus
    cascaded_document_ids: list[str] | None = Field(default=None, alias="cascadedDocumentIds")


class VerifyArtifactOptions(BaseModel):
    """Reserved verification options for future storage backends."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["head_only", "hash_verify"] | None = None


class VerificationResult(BaseModel):
    """Provider verification result."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["verified", "failed", "unsupported"]
    details: dict[str, Any] | None = None
    reason: str | None = None


class StorageCapabilities(BaseModel):
    """Direct storage API capability snapshot."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider: str
    addressing: list[StorageAddressingMode]
    consistency: StorageConsistency
    max_upload_bytes: int | None = Field(default=None, alias="maxUploadBytes")
    min_upload_bytes: int | None = Field(default=None, alias="minUploadBytes")
    supports_direct_upload: bool = Field(alias="supportsDirectUpload")
    supports_range_read: bool = Field(alias="supportsRangeRead")
    supports_delete: bool = Field(alias="supportsDelete")
    supports_tombstone: bool = Field(alias="supportsTombstone")
    supports_bundles: bool = Field(alias="supportsBundles")
    supported_bundle_formats: list[str] = Field(alias="supportedBundleFormats")
    supports_verification: bool = Field(alias="supportsVerification")
    supports_provider_proofs: bool = Field(alias="supportsProviderProofs")
    supports_replication: bool = Field(alias="supportsReplication")
    supports_retrieval_status: bool = Field(alias="supportsRetrievalStatus")
    supports_content_hash: bool = Field(alias="supportsContentHash")
    supports_content_addressed_uri: bool = Field(alias="supportsContentAddressedUri")
    delete_semantics: list[StorageDeleteSemantics] = Field(alias="deleteSemantics")
    availability_model: StorageAvailabilityModel = Field(alias="availabilityModel")
