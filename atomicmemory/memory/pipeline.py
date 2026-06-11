"""Memory processing pipeline hooks — sync and async surfaces.

Port of ``atomicmemory-sdk/src/memory/pipeline.ts``. Pipelines let
providers (or wrappers) preprocess/postprocess ingest, search, get, and
list operations without modifying the provider itself.

The Python SDK mirrors the repo's dual service surface: ``MemoryProcessingPipeline``
carries plain (non-awaitable) callables for ``MemoryService`` (sync); the
async counterpart ``AsyncMemoryProcessingPipeline`` carries ``Awaitable``-returning
callables for ``AsyncMemoryService``. TS is async-only and has one type, so this
split is Python-specific. Before 1.2.0 the hooks were accepted at registration
time but never invoked, so retyping the sync fields is observable only to
constructors of pipelines — which received no behaviour before this release.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from atomicmemory.memory.types import (
    IngestInput,
    IngestResult,
    ListRequest,
    ListResultPage,
    Memory,
    MemoryRef,
    SearchRequest,
    SearchResultPage,
)


@dataclass(frozen=True)
class MemoryProcessingPipeline:
    """Optional hook bundle for a sync provider.

    Each hook may be ``None``. When present, ``MemoryService`` calls it
    synchronously around the corresponding provider call.

    Hook exceptions propagate unwrapped to the caller — hooks are
    caller-supplied code, so the service does not normalize them into
    ``AtomicMemoryError`` subclasses the way provider errors are wrapped.
    """

    preprocess_ingest: Callable[[IngestInput], list[IngestInput]] | None = None
    postprocess_ingest: Callable[[IngestResult, IngestInput], None] | None = None
    preprocess_search: Callable[[SearchRequest], SearchRequest] | None = None
    postprocess_search: Callable[[SearchResultPage, SearchRequest], SearchResultPage] | None = None
    preprocess_get: Callable[[MemoryRef], MemoryRef] | None = None
    postprocess_get: Callable[[Memory | None, MemoryRef], Memory | None] | None = None
    postprocess_list: Callable[[ListResultPage, ListRequest], ListResultPage] | None = None


@dataclass(frozen=True)
class AsyncMemoryProcessingPipeline:
    """Optional hook bundle for an async provider.

    Each hook may be ``None``. When present, ``AsyncMemoryService`` awaits it
    around the corresponding provider call.

    Hook exceptions propagate unwrapped to the caller — hooks are
    caller-supplied code, so the service does not normalize them into
    ``AtomicMemoryError`` subclasses the way provider errors are wrapped.
    """

    preprocess_ingest: Callable[[IngestInput], Awaitable[list[IngestInput]]] | None = None
    postprocess_ingest: Callable[[IngestResult, IngestInput], Awaitable[None]] | None = None
    preprocess_search: Callable[[SearchRequest], Awaitable[SearchRequest]] | None = None
    postprocess_search: Callable[[SearchResultPage, SearchRequest], Awaitable[SearchResultPage]] | None = None
    preprocess_get: Callable[[MemoryRef], Awaitable[MemoryRef]] | None = None
    postprocess_get: Callable[[Memory | None, MemoryRef], Awaitable[Memory | None]] | None = None
    postprocess_list: Callable[[ListResultPage, ListRequest], Awaitable[ListResultPage]] | None = None


NOOP_PIPELINE = MemoryProcessingPipeline()
NOOP_ASYNC_PIPELINE = AsyncMemoryProcessingPipeline()
