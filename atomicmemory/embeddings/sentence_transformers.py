"""Sentence-Transformers adapter — local embeddings via the ``embeddings`` extra.

Port of the WASM/transformers.js path in
`atomicmemory-sdk/src/embedding/transformers-adapter.ts`. Default
model is ``sentence-transformers/all-MiniLM-L6-v2`` (384 dims), matching
the TS SDK's ``Xenova/all-MiniLM-L6-v2``.

Lazy-imports ``sentence_transformers`` at construction time. If the
extra was not installed, a clear actionable error is raised.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from atomicmemory.core.errors import ConfigError
from atomicmemory.embeddings.base import EmbeddingResult

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSIONS = 384


def _import_sentence_transformers() -> Any:
    try:
        import sentence_transformers
    except ImportError as exc:
        raise ConfigError(
            "atomicmemory[embeddings] is not installed. "
            "Install the optional extra: pip install 'atomicmemory[embeddings]'.",
            context={"missing_dependency": "sentence_transformers"},
        ) from exc
    return sentence_transformers


class SentenceTransformersAdapter:
    """Local embedding adapter backed by ``sentence-transformers``.

    Loads the model lazily on first use; subsequent calls reuse the
    same in-memory instance.
    """

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
        normalize: bool = True,
        device: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._normalize = normalize
        self._device = device
        self._model: SentenceTransformer | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _ensure_model(self) -> Any:
        if self._model is None:
            module = _import_sentence_transformers()
            self._model = module.SentenceTransformer(self._model_name, device=self._device)
        return self._model

    def embed(self, text: str) -> EmbeddingResult:
        model = self._ensure_model()
        start = time.monotonic()
        vector = model.encode(text, normalize_embeddings=self._normalize)
        return EmbeddingResult(
            embedding=[float(x) for x in vector.tolist()],
            dimensions=self._dimensions,
            model=self._model_name,
            processing_time_seconds=time.monotonic() - start,
            provider="sentence-transformers",
        )

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        if not texts:
            return []
        model = self._ensure_model()
        start = time.monotonic()
        vectors = model.encode(list(texts), normalize_embeddings=self._normalize)
        elapsed = time.monotonic() - start
        per_item = elapsed / len(texts) if texts else 0.0
        return [
            EmbeddingResult(
                embedding=[float(x) for x in v.tolist()],
                dimensions=self._dimensions,
                model=self._model_name,
                processing_time_seconds=per_item,
                provider="sentence-transformers",
            )
            for v in vectors
        ]
