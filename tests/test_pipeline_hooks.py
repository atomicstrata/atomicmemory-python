"""Hook-order tests for the sync service pipeline execution.

TS has NO pipeline tests (verified 2026-06-11) — these are written fresh from
the memory-service.ts:109-200 semantics, which remain the contract:
preprocess_ingest may split one input into many; each per-item result passes
through postprocess_ingest; the service returns the concatenated merge.
"""

from __future__ import annotations

from typing import Any

from atomicmemory.memory.pipeline import (
    NOOP_ASYNC_PIPELINE,
    NOOP_PIPELINE,
    AsyncMemoryProcessingPipeline,
    MemoryProcessingPipeline,
)
from atomicmemory.memory.registry import (
    AsyncProviderRegistration,
    ProviderRegistration,
    ProviderRegistry,
)
from atomicmemory.memory.service import MemoryService, MemoryServiceConfig
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
    RecordingProvider,
    _make_service,
)


def test_sync_and_async_pipelines_are_distinct_types() -> None:
    assert type(NOOP_PIPELINE) is MemoryProcessingPipeline
    assert type(NOOP_ASYNC_PIPELINE) is AsyncMemoryProcessingPipeline


def test_registrations_default_to_their_surface_noop() -> None:
    sync_reg = ProviderRegistration.__dataclass_fields__["pipeline"]
    async_reg = AsyncProviderRegistration.__dataclass_fields__["pipeline"]
    assert sync_reg.default is NOOP_PIPELINE
    assert async_reg.default is NOOP_ASYNC_PIPELINE


def test_preprocess_split_ingests_each_and_merges_in_order() -> None:
    log: list[tuple[str, Any]] = []
    split = [TextIngest(content="a", scope=_SCOPE), TextIngest(content="b", scope=_SCOPE)]
    pipeline = MemoryProcessingPipeline(
        preprocess_ingest=lambda i: (log.append(("pre", i)), split)[1],
        postprocess_ingest=lambda r, i: log.append(("post", r, i)),
    )
    provider = RecordingProvider(
        ingest_results=[IngestResult(created=["m1"]), IngestResult(created=["m2"], updated=["u1"])]
    )
    service = _make_service(provider, pipeline)
    result = service.ingest(TextIngest(content="orig", scope=_SCOPE))
    assert [c[1].content for c in provider.calls] == ["a", "b"]  # split inputs ingested, in order
    assert result == IngestResult(created=["m1", "m2"], updated=["u1"], unchanged=[])
    assert log[0][0] == "pre" and log[0][1].content == "orig"
    assert [(e[0], e[2].content) for e in log[1:]] == [("post", "a"), ("post", "b")]


def test_postprocess_search_receives_the_processed_request() -> None:
    seen: list[SearchRequest] = []
    rewritten = SearchRequest(query="rewritten", scope=_SCOPE)
    pipeline = MemoryProcessingPipeline(
        preprocess_search=lambda r: rewritten,
        postprocess_search=lambda page, req: (seen.append(req), page)[1],
    )
    provider = RecordingProvider()
    service = _make_service(provider, pipeline)
    service.search(SearchRequest(query="orig", scope=_SCOPE))
    assert provider.calls == [("search", rewritten)]
    assert seen == [rewritten]  # TS passes the PROCESSED request to postprocess


def test_ingest_without_preprocess_single_call_with_postprocess() -> None:
    log: list[tuple[str, Any]] = []
    pipeline = MemoryProcessingPipeline(
        postprocess_ingest=lambda r, i: log.append(("post", r, i)),
    )
    provider = RecordingProvider(ingest_results=[IngestResult(created=["m1"])])
    service = _make_service(provider, pipeline)
    original = TextIngest(content="x", scope=_SCOPE)
    result = service.ingest(original)
    assert result == IngestResult(created=["m1"])
    assert len(provider.calls) == 1
    assert provider.calls[0] == ("ingest", original)
    assert log == [("post", IngestResult(created=["m1"]), original)]


def test_get_pre_and_postprocess_chain() -> None:
    seen_pre: list[MemoryRef] = []
    seen_post: list[MemoryRef] = []
    rewritten_ref = MemoryRef(id="new-id", scope=_SCOPE)
    pipeline = MemoryProcessingPipeline(
        preprocess_get=lambda ref: (seen_pre.append(ref), rewritten_ref)[1],
        postprocess_get=lambda mem, ref: (seen_post.append(ref), mem)[1],
    )
    provider = RecordingProvider()
    service = _make_service(provider, pipeline)
    original_ref = MemoryRef(id="orig-id", scope=_SCOPE)
    service.get(original_ref)
    # Provider received the PROCESSED ref
    assert provider.calls == [("get", rewritten_ref)]
    # Preprocess got the original; postprocess got the processed ref
    assert seen_pre == [original_ref]
    assert seen_post == [rewritten_ref]


def test_list_postprocess_only() -> None:
    replacement = ListResultPage(memories=[])
    seen_pages: list[ListResultPage] = []
    seen_reqs: list[ListRequest] = []
    pipeline = MemoryProcessingPipeline(
        postprocess_list=lambda page, req: (seen_pages.append(page), seen_reqs.append(req), replacement)[2],
    )
    provider = RecordingProvider()
    service = _make_service(provider, pipeline)
    request = ListRequest(scope=_SCOPE)
    result = service.list(request)
    # Provider receives the ORIGINAL request (no preprocess for list)
    assert provider.calls == [("list", request)]
    assert seen_reqs == [request]
    assert result is replacement


def test_delete_and_package_ignore_pipeline_hooks() -> None:
    pre_calls: list[Any] = []
    post_calls: list[Any] = []
    pipeline = MemoryProcessingPipeline(
        preprocess_ingest=lambda i: (pre_calls.append(i), [i])[1],
        postprocess_ingest=lambda r, i: post_calls.append((r, i)),
        preprocess_search=lambda r: (pre_calls.append(r), r)[1],
        postprocess_search=lambda p, r: (post_calls.append((p, r)), p)[1],
    )
    provider = RecordingProvider()
    service = _make_service(provider, pipeline)
    ref = MemoryRef(id="x", scope=_SCOPE)
    service.delete(ref)
    service.package(PackageRequest(query="q", scope=_SCOPE))
    assert pre_calls == []
    assert post_calls == []


def test_preprocess_returning_empty_list_produces_empty_result() -> None:
    pipeline = MemoryProcessingPipeline(preprocess_ingest=lambda i: [])
    provider = RecordingProvider()
    service = _make_service(provider, pipeline)
    result = service.ingest(TextIngest(content="x", scope=_SCOPE))
    assert result == IngestResult(created=[], updated=[], unchanged=[])
    assert provider.calls == []


def test_noop_pipeline_is_passthrough() -> None:
    provider = RecordingProvider(ingest_results=[IngestResult(created=["m1"])])
    service = _make_service(provider, NOOP_PIPELINE)
    original = TextIngest(content="hello", scope=_SCOPE)
    result = service.ingest(original)
    assert result == IngestResult(created=["m1"])
    assert provider.calls == [("ingest", original)]


def test_named_provider_uses_its_own_pipeline() -> None:
    log_a: list[Any] = []
    log_b: list[Any] = []
    pipeline_a = MemoryProcessingPipeline(
        postprocess_ingest=lambda r, i: log_a.append(("post_a", i)),
    )
    provider_a = RecordingProvider(ingest_results=[IngestResult(created=["ma"])])
    provider_b = RecordingProvider(ingest_results=[IngestResult(created=["mb"])])
    registry = ProviderRegistry()
    registry.register("a", lambda _cfg: ProviderRegistration(provider=provider_a, pipeline=pipeline_a))
    registry.register("b", lambda _cfg: ProviderRegistration(provider=provider_b))
    service = MemoryService(MemoryServiceConfig(default_provider="a", provider_configs={"a": {}, "b": {}}))
    service.initialize(registry)
    service.ingest(TextIngest(content="x", scope=_SCOPE), provider_name="a")
    service.ingest(TextIngest(content="y", scope=_SCOPE), provider_name="b")
    assert log_a == [("post_a", TextIngest(content="x", scope=_SCOPE))]
    assert log_b == []  # provider b has noop pipeline — no hooks fired


def test_client_ingest_and_ingest_direct_both_run_pipeline() -> None:
    """Both client.ingest and client.ingest_direct run the service pipeline.

    TS reference: memory-client.ts:120-133 — ingestDirect calls
    this.service.ingest() identically to ingest(). 'direct' bypasses
    application-wrapper gating, never the pipeline.
    """
    from atomicmemory.client.memory_client import MemoryClient

    log: list[Any] = []
    pipeline = MemoryProcessingPipeline(
        postprocess_ingest=lambda r, i: log.append(("post", i)),
    )
    provider = RecordingProvider(ingest_results=[IngestResult(created=["m1"]), IngestResult(created=["m2"])])
    registry = ProviderRegistry()
    registry.register("recording", lambda _cfg: ProviderRegistration(provider=provider, pipeline=pipeline))
    client = MemoryClient(providers={"recording": {}})
    client.initialize(registry)
    input_a = TextIngest(content="a", scope=_SCOPE)
    input_b = TextIngest(content="b", scope=_SCOPE)
    client.ingest(input_a)
    client.ingest_direct(input_b)
    client.close()
    assert len(log) == 2
    assert log[0] == ("post", input_a)
    assert log[1] == ("post", input_b)
