"""Optional local embeddings — gated behind the ``embeddings`` extra.

Install with ``pip install 'atomicmemory[embeddings]'`` to pull in
``sentence-transformers``. Without the extra, importing
:class:`SentenceTransformersAdapter` raises a clear actionable error;
the protocol :class:`EmbeddingGenerator` itself is always available.
"""

from atomicmemory.embeddings.base import EmbeddingGenerator, EmbeddingResult
from atomicmemory.embeddings.sentence_transformers import SentenceTransformersAdapter

__all__ = [
    "EmbeddingGenerator",
    "EmbeddingResult",
    "SentenceTransformersAdapter",
]
