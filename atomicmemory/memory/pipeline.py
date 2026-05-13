"""Memory processing pipeline hooks.

Port of `atomicmemory-sdk/src/memory/pipeline.ts`. Pipelines let
providers (or wrappers) preprocess/postprocess ingest, search, get, and
list operations without modifying the provider itself.
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
    """Optional hook bundle for a provider.

    Each hook may be ``None``. When present, the service awaits it around
    the corresponding provider call.
    """

    preprocess_ingest: Callable[[IngestInput], Awaitable[list[IngestInput]]] | None = None
    postprocess_ingest: Callable[[IngestResult, IngestInput], Awaitable[None]] | None = None
    preprocess_search: Callable[[SearchRequest], Awaitable[SearchRequest]] | None = None
    postprocess_search: Callable[[SearchResultPage, SearchRequest], Awaitable[SearchResultPage]] | None = None
    preprocess_get: Callable[[MemoryRef], Awaitable[MemoryRef]] | None = None
    postprocess_get: Callable[[Memory | None, MemoryRef], Awaitable[Memory | None]] | None = None
    postprocess_list: Callable[[ListResultPage, ListRequest], Awaitable[ListResultPage]] | None = None


NOOP_PIPELINE = MemoryProcessingPipeline()
