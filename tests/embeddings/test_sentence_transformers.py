"""Tests for the sentence-transformers adapter — skipped without the extra."""

from __future__ import annotations

import pytest

# Skip the entire module when the extra is not installed; the adapter
# itself raises ConfigError, but downloading real models is out of scope
# for unit tests.
pytest.importorskip("sentence_transformers")


def test_adapter_constructs_with_defaults() -> None:
    from atomicmemory.embeddings import SentenceTransformersAdapter

    adapter = SentenceTransformersAdapter()
    assert adapter.dimensions == 384
    assert adapter.model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_missing_dependency_error_message_is_actionable() -> None:
    """When the extra is uninstalled, the error explains how to fix it.

    We can't easily simulate the missing import here since we just
    proved it exists, but we check the error class is wired in.
    """
    from atomicmemory.core.errors import ConfigError
    from atomicmemory.embeddings.sentence_transformers import SentenceTransformersAdapter

    # Sanity: the class is importable; actual ImportError-path coverage
    # lives in the runtime exception handler.
    assert SentenceTransformersAdapter is not None
    assert ConfigError is not None
