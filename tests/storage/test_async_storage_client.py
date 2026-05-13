"""Tests for the async backend artifact-storage client."""

from __future__ import annotations

import httpx
import pytest
import respx

from atomicmemory.storage import ArtifactInUseError, AsyncStorageClient
from tests.storage.test_storage_client import _artifact, _capabilities


@pytest.mark.asyncio
@respx.mock
async def test_async_capabilities_sends_auth_and_user_header() -> None:
    route = respx.get("http://core.test/v1/storage/capabilities").mock(
        return_value=httpx.Response(200, json=_capabilities()),
    )
    async with AsyncStorageClient({"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}) as client:
        caps = await client.capabilities()

    request = route.calls[0].request
    assert caps.provider == "local_fs"
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.headers["X-AtomicMemory-User-Id"] == "u1"


@pytest.mark.asyncio
@respx.mock
async def test_async_put_managed_sends_content_length() -> None:
    route = respx.post("http://core.test/v1/storage/artifacts?mode=managed").mock(
        return_value=httpx.Response(200, json=_artifact()),
    )
    async with AsyncStorageClient({"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}) as client:
        artifact = await client.put({"mode": "managed", "body": b"body", "contentType": "text/plain"})

    assert artifact.artifact_id == "a1"
    assert route.calls[0].request.headers["Content-Length"] == "4"


@pytest.mark.asyncio
@respx.mock
async def test_async_delete_maps_artifact_in_use_error() -> None:
    respx.delete("http://core.test/v1/storage/artifacts/a1").mock(
        return_value=httpx.Response(409, json={"error_code": "artifact_in_use", "referenced_by_document_count": 1}),
    )
    async with AsyncStorageClient({"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}) as client:
        with pytest.raises(ArtifactInUseError):
            await client.delete({"artifact_id": "a1"})


@pytest.mark.asyncio
@respx.mock
async def test_async_stream_content_reads_response_inside_context() -> None:
    route = respx.get("http://core.test/v1/storage/artifacts/a1/content").mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(b"abcdef")),
    )
    async with (
        AsyncStorageClient({"apiUrl": "http://core.test", "apiKey": "secret", "userId": "u1"}) as client,
        client.stream_content({"artifact_id": "a1"}) as response,
    ):
        body = b"".join([chunk async for chunk in response.aiter_bytes()])

    assert body == b"abcdef"
    assert route.called
