"""Hook-order tests for the async service pipeline execution.

Mirrors tests/test_pipeline_hooks.py exactly but uses AsyncMemoryProcessingPipeline,
async hook lambdas, and AsyncMemoryService. asyncio_mode=auto (pyproject.toml)
so plain async def test_ functions run under the event loop automatically.
"""

from __future__ import annotations

from typing import Any

from atomicmemory.memory.pipeline import (
    NOOP_ASYNC_PIPELINE,
    AsyncMemoryProcessingPipeline,
)
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    AsyncProviderRegistry,
)
from atomicmemory.memory.service import AsyncMemoryService, MemoryServiceConfig
from atomicmemory.memory.types import (
    IngestResult,
    ListRequest,
    ListResultPage,
    MemoryRef,
    PackageRequest,
    SearchRequest,
    TextIngest,
)
from tests._pipeline_fakes import (
    _SCOPE,
    AsyncRecordingProvider,
    _make_async_service,
)


async def test_async_preprocess_split_ingests_each_and_merges_in_order() -> None:
    log: list[tuple[str, Any]] = []
    split = [TextIngest(content="a", scope=_SCOPE), TextIngest(content="b", scope=_SCOPE)]

    async def _pre(i: Any) -> list[Any]:
        log.append(("pre", i))
        return split

    async def _post(r: Any, i: Any) -> None:
        log.append(("post", r, i))

    pipeline = AsyncMemoryProcessingPipeline(preprocess_ingest=_pre, postprocess_ingest=_post)
    provider = AsyncRecordingProvider(
        ingest_results=[IngestResult(created=["m1"]), IngestResult(created=["m2"], updated=["u1"])]
    )
    service = await _make_async_service(provider, pipeline)
    result = await service.ingest(TextIngest(content="orig", scope=_SCOPE))
    assert [c[1].content for c in provider.calls] == ["a", "b"]
    assert result == IngestResult(created=["m1", "m2"], updated=["u1"], unchanged=[])
    assert log[0][0] == "pre" and log[0][1].content == "orig"
    assert [(e[0], e[2].content) for e in log[1:]] == [("post", "a"), ("post", "b")]


async def test_async_postprocess_search_receives_the_processed_request() -> None:
    seen: list[SearchRequest] = []
    rewritten = SearchRequest(query="rewritten", scope=_SCOPE)

    async def _pre(r: SearchRequest) -> SearchRequest:
        return rewritten

    async def _post(page: Any, req: SearchRequest) -> Any:
        seen.append(req)
        return page

    pipeline = AsyncMemoryProcessingPipeline(preprocess_search=_pre, postprocess_search=_post)
    provider = AsyncRecordingProvider()
    service = await _make_async_service(provider, pipeline)
    await service.search(SearchRequest(query="orig", scope=_SCOPE))
    assert provider.calls == [("search", rewritten)]
    assert seen == [rewritten]  # TS passes the PROCESSED request to postprocess


async def test_async_ingest_without_preprocess_single_call_with_postprocess() -> None:
    log: list[tuple[str, Any]] = []

    async def _post(r: Any, i: Any) -> None:
        log.append(("post", r, i))

    pipeline = AsyncMemoryProcessingPipeline(postprocess_ingest=_post)
    provider = AsyncRecordingProvider(ingest_results=[IngestResult(created=["m1"])])
    service = await _make_async_service(provider, pipeline)
    original = TextIngest(content="x", scope=_SCOPE)
    result = await service.ingest(original)
    assert result == IngestResult(created=["m1"])
    assert len(provider.calls) == 1
    assert provider.calls[0] == ("ingest", original)
    assert log == [("post", IngestResult(created=["m1"]), original)]


async def test_async_get_pre_and_postprocess_chain() -> None:
    seen_pre: list[MemoryRef] = []
    seen_post: list[MemoryRef] = []
    rewritten_ref = MemoryRef(id="new-id", scope=_SCOPE)

    async def _pre(ref: MemoryRef) -> MemoryRef:
        seen_pre.append(ref)
        return rewritten_ref

    async def _post(mem: Any, ref: MemoryRef) -> Any:
        seen_post.append(ref)
        return mem

    pipeline = AsyncMemoryProcessingPipeline(preprocess_get=_pre, postprocess_get=_post)
    provider = AsyncRecordingProvider()
    service = await _make_async_service(provider, pipeline)
    original_ref = MemoryRef(id="orig-id", scope=_SCOPE)
    await service.get(original_ref)
    assert provider.calls == [("get", rewritten_ref)]
    assert seen_pre == [original_ref]
    assert seen_post == [rewritten_ref]


async def test_async_list_postprocess_only() -> None:
    replacement = ListResultPage(memories=[])
    seen_pages: list[ListResultPage] = []
    seen_reqs: list[ListRequest] = []

    async def _post(page: ListResultPage, req: ListRequest) -> ListResultPage:
        seen_pages.append(page)
        seen_reqs.append(req)
        return replacement

    pipeline = AsyncMemoryProcessingPipeline(postprocess_list=_post)
    provider = AsyncRecordingProvider()
    service = await _make_async_service(provider, pipeline)
    request = ListRequest(scope=_SCOPE)
    result = await service.list(request)
    assert provider.calls == [("list", request)]
    assert seen_reqs == [request]
    assert result is replacement


async def test_async_delete_and_package_ignore_pipeline_hooks() -> None:
    pre_calls: list[Any] = []
    post_calls: list[Any] = []

    async def _pre_ingest(i: Any) -> list[Any]:
        pre_calls.append(i)
        return [i]

    async def _post_ingest(r: Any, i: Any) -> None:
        post_calls.append((r, i))

    async def _pre_search(r: Any) -> Any:
        pre_calls.append(r)
        return r

    async def _post_search(p: Any, r: Any) -> Any:
        post_calls.append((p, r))
        return p

    pipeline = AsyncMemoryProcessingPipeline(
        preprocess_ingest=_pre_ingest,
        postprocess_ingest=_post_ingest,
        preprocess_search=_pre_search,
        postprocess_search=_post_search,
    )
    provider = AsyncRecordingProvider()
    service = await _make_async_service(provider, pipeline)
    ref = MemoryRef(id="x", scope=_SCOPE)
    await service.delete(ref)
    await service.package(PackageRequest(query="q", scope=_SCOPE))
    assert pre_calls == []
    assert post_calls == []


async def test_async_preprocess_returning_empty_list_produces_empty_result() -> None:
    async def _pre(i: Any) -> list[Any]:
        return []

    pipeline = AsyncMemoryProcessingPipeline(preprocess_ingest=_pre)
    provider = AsyncRecordingProvider()
    service = await _make_async_service(provider, pipeline)
    result = await service.ingest(TextIngest(content="x", scope=_SCOPE))
    assert result == IngestResult(created=[], updated=[], unchanged=[])
    assert provider.calls == []


async def test_async_noop_pipeline_is_passthrough() -> None:
    provider = AsyncRecordingProvider(ingest_results=[IngestResult(created=["m1"])])
    service = await _make_async_service(provider, NOOP_ASYNC_PIPELINE)
    original = TextIngest(content="hello", scope=_SCOPE)
    result = await service.ingest(original)
    assert result == IngestResult(created=["m1"])
    assert provider.calls == [("ingest", original)]


async def test_async_named_provider_uses_its_own_pipeline() -> None:
    log_a: list[Any] = []

    async def _post_a(r: Any, i: Any) -> None:
        log_a.append(("post_a", i))

    pipeline_a = AsyncMemoryProcessingPipeline(postprocess_ingest=_post_a)
    provider_a = AsyncRecordingProvider(ingest_results=[IngestResult(created=["ma"])])
    provider_b = AsyncRecordingProvider(ingest_results=[IngestResult(created=["mb"])])
    registry = AsyncProviderRegistry()
    registry.register("a", lambda _cfg: AsyncProviderRegistration(provider=provider_a, pipeline=pipeline_a))
    registry.register("b", lambda _cfg: AsyncProviderRegistration(provider=provider_b))
    service = AsyncMemoryService(MemoryServiceConfig(default_provider="a", provider_configs={"a": {}, "b": {}}))
    await service.initialize(registry)
    await service.ingest(TextIngest(content="x", scope=_SCOPE), provider_name="a")
    await service.ingest(TextIngest(content="y", scope=_SCOPE), provider_name="b")
    assert log_a == [("post_a", TextIngest(content="x", scope=_SCOPE))]


async def test_async_client_ingest_and_ingest_direct_both_run_pipeline() -> None:
    """Both async client.ingest and client.ingest_direct run the service pipeline.

    TS reference: memory-client.ts:120-133 — ingestDirect calls
    this.service.ingest() identically to ingest(). 'direct' bypasses
    application-wrapper gating, never the pipeline.
    """
    from atomicmemory.client.async_memory_client import AsyncMemoryClient

    log: list[Any] = []

    async def _post(r: Any, i: Any) -> None:
        log.append(("post", i))

    pipeline = AsyncMemoryProcessingPipeline(postprocess_ingest=_post)
    provider = AsyncRecordingProvider(ingest_results=[IngestResult(created=["m1"]), IngestResult(created=["m2"])])
    registry = AsyncProviderRegistry()
    registry.register(
        "async-recording",
        lambda _cfg: AsyncProviderRegistration(provider=provider, pipeline=pipeline),
    )
    client = AsyncMemoryClient(providers={"async-recording": {}})
    await client.initialize(registry)
    input_a = TextIngest(content="a", scope=_SCOPE)
    input_b = TextIngest(content="b", scope=_SCOPE)
    await client.ingest(input_a)
    await client.ingest_direct(input_b)
    await client.close()
    assert len(log) == 2
    assert log[0] == ("post", input_a)
    assert log[1] == ("post", input_b)
