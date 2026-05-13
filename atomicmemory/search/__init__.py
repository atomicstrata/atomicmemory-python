"""Local search primitives — similarity, chunking, ranking, and orchestration.

Port of `atomicmemory-sdk/src/search/` and the chunking helpers at
`src/utils/chunking.ts`. These are pure Python (numpy + stdlib) and work
without any provider configured — useful for offline experiments,
fixture-driven benchmarks, and embedding the SDK in non-Atomicmem
contexts.
"""

from atomicmemory.search.chunking import (
    ChunkOptions,
    ChunkResult,
    chunk_by_paragraphs,
    chunk_by_sentences,
    chunk_text,
    chunk_text_with_metadata,
)
from atomicmemory.search.ranking import RankingConfig, rerank
from atomicmemory.search.semantic_search import (
    SemanticSearch,
    SemanticSearchConfig,
    SemanticSearchResult,
    StoredContext,
)
from atomicmemory.search.similarity import (
    cosine_similarity,
    find_top_k,
    rank_by_similarity,
)

__all__ = [
    "ChunkOptions",
    "ChunkResult",
    "RankingConfig",
    "SemanticSearch",
    "SemanticSearchConfig",
    "SemanticSearchResult",
    "StoredContext",
    "chunk_by_paragraphs",
    "chunk_by_sentences",
    "chunk_text",
    "chunk_text_with_metadata",
    "cosine_similarity",
    "find_top_k",
    "rank_by_similarity",
    "rerank",
]
