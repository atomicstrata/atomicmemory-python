"""Embedding adapter protocol + result type.

Port of `atomicmemory-sdk/src/embedding/embedding-generator.ts`'s
public surface. Implementations live in sibling modules
(``sentence_transformers.py``, future others).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class EmbeddingResult:
    """A single embedding with provenance metadata."""

    embedding: list[float]
    dimensions: int
    model: str
    processing_time_seconds: float
    provider: str
    cache_hit: bool = False


@runtime_checkable
class EmbeddingGenerator(Protocol):
    """Common contract for any embedding backend."""

    @property
    def dimensions(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    def embed(self, text: str) -> EmbeddingResult: ...

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]: ...
