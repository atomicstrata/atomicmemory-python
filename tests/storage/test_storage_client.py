"""Tests for the backend artifact-storage client."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from atomicmemory.storage import (
    ArtifactInUseError,
    ArtifactNotFoundError,
    ArtifactRange,
    FilecoinDirectStorageNotSupportedError,
    PointerContentNotManagedError,
    StorageClient,
    StorageClientError,
)

_CONFIG = {"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}


def _artifact(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "artifact_id": "a1",
        "provider": "local_fs",
        "mode": "managed",
        "uri": "file:///tmp/a1.bin",
        "status": "stored",
        "size_bytes": 4,
        "content_type": "text/plain",
        "content_encoding": "identity",
        "identifiers": {"key": "value"},
        "lifecycle": {"availability": "immediate", "deleteSemantics": "delete"},
        "metadata": {"source": "test"},
        "created_at": "2026-05-12T00:00:00Z",
        "updated_at": "2026-05-12T00:00:00Z",
    }
    base.update(overrides)
    return base


def _capabilities() -> dict[str, object]:
    return {
        "provider": "local_fs",
        "addressing": ["location"],
        "consistency": "immediate",
        "supportsDirectUpload": True,
        "supportsRangeRead": False,
        "supportsDelete": True,
        "supportsTombstone": False,
        "supportsBundles": False,
        "supportedBundleFormats": [],
        "supportsVerification": True,
        "supportsProviderProofs": False,
        "supportsReplication": False,
        "supportsRetrievalStatus": False,
        "supportsContentHash": True,
        "supportsContentAddressedUri": False,
        "deleteSemantics": ["delete"],
        "availabilityModel": "immediate",
    }


@respx.mock
def test_capabilities_sends_auth_and_user_header_without_query_user_id() -> None:
    route = respx.get("http://core.test/v1/storage/capabilities").mock(
        return_value=httpx.Response(200, json=_capabilities()),
    )
    with StorageClient(_CONFIG) as client:
        caps = client.capabilities()

    request = route.calls[0].request
    assert caps.supports_direct_upload is True
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.headers["X-AtomicMemory-User-Id"] == "u1"
    assert "user_id" not in str(request.url)


@respx.mock
def test_put_pointer_serializes_snake_case_wire_body() -> None:
    route = respx.post("http://core.test/v1/storage/artifacts").mock(
        return_value=httpx.Response(200, json=_artifact(mode="pointer", uri="https://x.test/file.pdf")),
    )
    with StorageClient(_CONFIG) as client:
        artifact = client.put({"mode": "pointer", "uri": "https://x.test/file.pdf", "contentType": "application/pdf"})

    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body == {"mode": "pointer", "uri": "https://x.test/file.pdf", "content_type": "application/pdf"}
    assert artifact.artifact_id == "a1"


@respx.mock
def test_put_managed_sends_known_length_bytes_and_metadata_header() -> None:
    route = respx.post("http://core.test/v1/storage/artifacts?mode=managed&disclose_content_hash=true").mock(
        return_value=httpx.Response(200, json=_artifact(content_hash="sha256:x")),
    )
    with StorageClient(_CONFIG) as client:
        artifact = client.put(
            {
                "mode": "managed",
                "body": b"body",
                "contentType": "text/plain",
                "discloseContentHash": True,
                "metadata": {"x": 1},
            },
        )

    request = route.calls[0].request
    metadata = json.loads(base64.b64decode(request.headers["X-AtomicMemory-Metadata"]))
    assert request.content == b"body"
    assert request.headers["Content-Length"] == "4"
    assert metadata == {"x": 1}
    assert artifact.content_hash == "sha256:x"


def test_put_managed_rejects_string_body_without_leaking_input() -> None:
    with StorageClient(_CONFIG) as client, pytest.raises(StorageClientError) as excinfo:
        client.put({"mode": "managed", "body": "secret-body", "contentType": "text/plain"})

    assert excinfo.value.error_code == "invalid_storage_input"
    assert "secret-body" not in str(excinfo.value.context)


@respx.mock
def test_get_head_delete_and_verify_map_storage_shapes() -> None:
    respx.get("http://core.test/v1/storage/artifacts/a1").mock(return_value=httpx.Response(200, json=_artifact()))
    respx.head("http://core.test/v1/storage/artifacts/a1").mock(return_value=_head_response())
    respx.delete("http://core.test/v1/storage/artifacts/a1?policy=with_documents").mock(
        return_value=httpx.Response(
            200,
            json={"artifact_id": "a1", "status": "deleted", "cascaded_document_ids": ["d1"]},
        ),
    )
    respx.post("http://core.test/v1/storage/artifacts/a1/verify").mock(
        return_value=httpx.Response(200, json={"kind": "verified", "details": {"ok": True}}),
    )
    with StorageClient(_CONFIG) as client:
        artifact = client.get({"artifactId": "a1"})
        head = client.head({"artifact_id": "a1"})
        deleted = client.delete({"artifact_id": "a1"}, {"policy": "with_documents"})
        verified = client.verify({"artifact_id": "a1"})

    assert artifact.provider == "local_fs"
    assert head.status == "stored"
    assert deleted.cascaded_document_ids == ["d1"]
    assert verified.kind == "verified"


@respx.mock
def test_stream_content_reads_response_inside_context() -> None:
    route = respx.get("http://core.test/v1/storage/artifacts/a1/content").mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(b"abcdef")),
    )
    with StorageClient(_CONFIG) as client, client.stream_content({"artifact_id": "a1"}) as response:
        body = b"".join(response.iter_bytes())

    assert body == b"abcdef"
    assert route.called


def _head_response() -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "x-atomicmemory-artifact-id": "a1",
            "x-atomicmemory-provider": "local_fs",
            "x-atomicmemory-storage-mode": "managed",
            "x-atomicmemory-storage-status": "stored",
            "content-length": "4",
            "content-type": "text/plain",
        },
    )


@respx.mock
def test_invalid_head_status_raises_typed_error() -> None:
    respx.head("http://core.test/v1/storage/artifacts/a1").mock(
        return_value=httpx.Response(
            200,
            headers={"x-atomicmemory-storage-mode": "managed", "x-atomicmemory-storage-status": "new"},
        ),
    )
    with StorageClient(_CONFIG) as client, pytest.raises(StorageClientError) as excinfo:
        client.head({"artifact_id": "a1"})

    assert excinfo.value.error_code == "invalid_head_response"


@respx.mock
def test_invalid_stored_artifact_response_rejects_camel_case_alias() -> None:
    respx.get("http://core.test/v1/storage/artifacts/a1").mock(
        return_value=httpx.Response(200, json={"artifactId": "a1", "status": "stored"}),
    )
    with StorageClient(_CONFIG) as client, pytest.raises(StorageClientError) as excinfo:
        client.get({"artifact_id": "a1"})

    assert excinfo.value.error_code == "invalid_storage_response"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("size_bytes", "4"),
        ("metadata", {"nested": {"x": 1}}),
        ("identifiers", {"cid": 1}),
        ("provider_details", "not-an-object"),
    ],
)
@respx.mock
def test_invalid_optional_artifact_fields_raise_storage_client_error(field: str, value: object) -> None:
    respx.get("http://core.test/v1/storage/artifacts/a1").mock(
        return_value=httpx.Response(200, json=_artifact(**{field: value})),
    )
    with StorageClient(_CONFIG) as client, pytest.raises(StorageClientError) as excinfo:
        client.get({"artifact_id": "a1"})

    assert excinfo.value.error_code == "invalid_storage_response"


@respx.mock
def test_invalid_capabilities_response_raises_storage_client_error() -> None:
    respx.get("http://core.test/v1/storage/capabilities").mock(
        return_value=httpx.Response(200, json={"provider": "local_fs"}),
    )
    with StorageClient(_CONFIG) as client, pytest.raises(StorageClientError) as excinfo:
        client.capabilities()

    assert excinfo.value.error_code == "invalid_storage_response"


@respx.mock
def test_storage_errors_are_mapped_to_specific_classes() -> None:
    respx.delete("http://core.test/v1/storage/artifacts/a1").mock(
        return_value=httpx.Response(409, json={"error_code": "artifact_in_use", "referenced_by_document_count": 2}),
    )
    with StorageClient(_CONFIG) as client, pytest.raises(ArtifactInUseError) as excinfo:
        client.delete({"artifact_id": "a1"})

    assert excinfo.value.referenced_by_document_count == 2


@pytest.mark.parametrize(
    ("error_code", "status", "error_type"),
    [
        ("pointer_content_not_managed", 409, PointerContentNotManagedError),
        ("filecoin_direct_storage_not_yet_supported", 501, FilecoinDirectStorageNotSupportedError),
        ("artifact_not_found", 404, ArtifactNotFoundError),
    ],
)
@respx.mock
def test_other_typed_error_mappings(error_code: str, status: int, error_type: type[Exception]) -> None:
    respx.get("http://core.test/v1/storage/artifacts/a1/content").mock(
        return_value=httpx.Response(status, json={"error_code": error_code, "uri": "https://x.test"}),
    )
    with StorageClient(_CONFIG) as client, pytest.raises(error_type):
        client.get_content({"artifact_id": "a1"})


@respx.mock
def test_network_errors_are_wrapped() -> None:
    respx.get("http://core.test/v1/storage/capabilities").mock(side_effect=httpx.ConnectError("boom"))
    with StorageClient(_CONFIG) as client, pytest.raises(StorageClientError) as excinfo:
        client.capabilities()

    assert excinfo.value.error_code == "network_error"


def test_artifact_range_validates_bounds() -> None:
    assert ArtifactRange(start=0, end=10).end == 10
    with pytest.raises(ValueError):
        ArtifactRange(start=10, end=5)
