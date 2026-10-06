"""Drive both public factories through real HTTP clients and a v1 contract server."""

from __future__ import annotations

import asyncio
import inspect
import json

import httpx
import pytest
import respx

from atomicmemory import (
    AsyncMemoryClient,
    ConfigError,
    MemoryClient,
    MemoryToolError,
    PendingIngestError,
    Scope,
    TextIngest,
    async_memory_tools,
    memory_tools,
)
from tests.tools.conftest import Backend


async def execute(tools, name, arguments):
    result = tools[name].execute(arguments)
    if inspect.isawaitable(result):
        result = await result
    return result.model_dump(mode="json", exclude_none=True)


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def configured(request, backend):
    config = {"atomicmemory": {"api_url": backend.url, "api_key": "test-secret"}}
    client = AsyncMemoryClient(config) if request.param else MemoryClient(config)
    factory = async_memory_tools if request.param else memory_tools
    if request.param:
        await client.initialize()
    else:
        client.initialize()
    try:
        yield client, factory
    finally:
        result = client.close()
        if inspect.isawaitable(result):
            await result


async def test_save_restart_recall_correction_and_actor_isolation(configured, backend):
    client, factory = configured
    tools = factory(client=client, user="alice")
    assert await execute(tools, "memory_ingest", {"content": "I prefer tea."}) == {
        "created": ["mem-1"],
        "updated": [],
        "unchanged": [],
    }
    # Reopen the actual client; no conversation state is kept in the tool factory.
    closed = client.close()
    if inspect.isawaitable(closed):
        await closed
    initialized = client.initialize()
    if inspect.isawaitable(initialized):
        await initialized
    recalled = await execute(factory(client=client, user="alice"), "memory_search", {"query": "drink"})
    assert recalled["results"][0]["content"] == "I prefer tea."
    assert recalled["results"][0]["version_id"] == "v-1"
    assert recalled["retrieval"]["trace_id"] == "trace-1"
    assert "metadata" not in recalled["results"][0]
    assert await execute(tools, "memory_ingest", {"content": "I now prefer coffee."}) == {
        "created": [],
        "updated": ["mem-1"],
        "unchanged": [],
    }
    assert (await execute(tools, "memory_search", {"query": "drink"}))["results"][0][
        "content"
    ] == "I now prefer coffee."
    assert (await execute(factory(client=client, user="bob"), "memory_search", {"query": "drink"}))["results"] == []
    assert all(r["auth"] == "Bearer test-secret" for r in backend.requests)
    assert backend.requests[0]["body"] == {
        "user_id": "alice",
        "conversation": "I prefer tea.",
        "source_site": "sdk",
        "source_url": "",
    }


@pytest.mark.parametrize(
    "name,args",
    [
        ("memory_ingest", {"content": "fact", "user": "bob"}),
        ("memory_search", {"query": "fact", "scope": {"user": "bob"}}),
        ("memory_ingest", {"content": "   "}),
        ("memory_search", {"query": "   "}),
        ("memory_search", {"query": "fact", "limit": True}),
        ("memory_search", {"query": "fact", "limit": 21}),
        ("memory_search", {"query": "fact", "limit": "5"}),
        ("memory_ingest", {"content": "a" * 32769}),
        ("memory_search", {"query": "a" * 4097}),
    ],
)
async def test_invalid_arguments_never_reach_http(configured, backend, name, args):
    client, factory = configured
    with pytest.raises(MemoryToolError, match=r"^Memory tool failed\.$"):
        await execute(factory(client=client, user="alice"), name, args)
    assert backend.requests == []


@pytest.mark.parametrize("user", ["", "  ", "project:example", " project:example", "a" * 257])
def test_invalid_trusted_user(user):
    for client, factory in [(MemoryClient, memory_tools), (AsyncMemoryClient, async_memory_tools)]:
        with pytest.raises(ConfigError, match="application-owned user"):
            factory(client=client({"atomicmemory": {"api_url": "http://localhost:17350"}}), user=user)


@pytest.mark.parametrize("status", [202, 401, 422, 429, 500, 503])
@pytest.mark.parametrize("name,args", [("memory_ingest", {"content": "fact"}), ("memory_search", {"query": "fact"})])
async def test_http_failures_are_safe_and_not_retried(configured, backend, status, name, args):
    if status == 202 and name == "memory_search":
        pytest.skip("202 is an ingest-specific protocol response")
    client, factory = configured
    backend.status = status
    with pytest.raises(MemoryToolError) as caught:
        await execute(factory(client=client, user="alice"), name, args)
    assert str(caught.value) == "Memory tool failed."
    assert "test-secret" not in repr(caught.value)
    assert "private-backend-detail" not in repr(caught.value)
    assert len(backend.requests) == 1


async def test_sdk_pending_ingest_is_explicit(configured, backend):
    client, _ = configured
    backend.status = 202
    with pytest.raises(PendingIngestError):
        result = client.ingest(TextIngest(content="fact", scope=Scope(user="alice")))
        if inspect.isawaitable(result):
            await result
    assert len(backend.requests) == 1


async def test_search_is_bounded_and_preserves_evidence(configured, backend: Backend):
    client, factory = configured
    backend.hits = [{"id": f"m-{n}", "content": "🙂" * 5000, "ranking_score": 0.0} for n in range(21)]
    output = await execute(factory(client=client, user="alice"), "memory_search", {"query": "fact", "limit": 20})
    assert len(output["results"]) == 20
    assert sum(len(hit["content"]) for hit in output["results"]) == 16384
    assert output["results"][0]["score"] == 0.0
    assert output["truncated"] is True
    assert output["retrieval"]["candidate_ids"] == [f"m-{n}" for n in range(21)]


async def test_default_schema_limits_and_no_identity(configured):
    client, factory = configured
    tools = factory(client=client, user="alice")
    assert set(tools) == {"memory_ingest", "memory_search"}
    assert set(tools["memory_ingest"].parameters["properties"]) == {"content"}
    assert set(tools["memory_search"].parameters["properties"]) == {"query", "limit"}
    assert tools["memory_search"].parameters["properties"]["limit"]["default"] == 5
    assert tools["memory_search"].parameters["additionalProperties"] is False
    assert "alice" not in json.dumps(tools["memory_search"].parameters)


@pytest.mark.parametrize("error", [httpx.ReadTimeout("test-secret"), httpx.ConnectError("test-secret")])
async def test_transport_errors_are_safe(configured, backend, error):
    client, factory = configured
    with respx.mock as router:
        route = router.post(f"{backend.url}/v1/memories/ingest").mock(side_effect=error)
        with pytest.raises(MemoryToolError, match=r"^Memory tool failed\.$"):
            await execute(factory(client=client, user="alice"), "memory_ingest", {"content": "fact"})
        assert route.call_count == 1


async def test_async_cancellation_propagates(configured, backend):
    client, factory = configured
    if not isinstance(client, AsyncMemoryClient):
        pytest.skip("sync tools do not expose async cancellation")

    attempts = []

    async def cancel(request):
        attempts.append(request.url.path)
        raise asyncio.CancelledError()

    with respx.mock as router:
        router.post(f"{backend.url}/v1/memories/ingest").mock(side_effect=cancel)
        with pytest.raises(asyncio.CancelledError):
            await execute(factory(client=client, user="alice"), "memory_ingest", {"content": "fact"})
        assert attempts == ["/v1/memories/ingest"]


@pytest.mark.parametrize(
    "response",
    [
        {"stored_memory_ids": "not-an-array"},
        {"stored_memory_ids": [""]},
        {"stored_memory_ids": [1]},
        {"updated_memory_ids": False},
    ],
)
async def test_malformed_receipts_fail_safely(configured, backend, response):
    client, factory = configured
    backend.ingest_response = response
    with pytest.raises(MemoryToolError, match=r"^Memory tool failed\.$"):
        await execute(factory(client=client, user="alice"), "memory_ingest", {"content": "fact"})
    assert len(backend.requests) == 1


async def test_empty_ingest_arrays_are_not_invented_success(configured, backend):
    client, factory = configured
    backend.ingest_response = {"stored_memory_ids": [], "updated_memory_ids": []}
    assert await execute(factory(client=client, user="alice"), "memory_ingest", {"content": "fact"}) == {
        "created": [],
        "updated": [],
        "unchanged": [],
    }
    assert len(backend.requests) == 1
