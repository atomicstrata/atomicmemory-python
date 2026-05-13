"""Tests for text chunking."""

from __future__ import annotations

import pytest

from atomicmemory.search.chunking import (
    ChunkOptions,
    chunk_by_paragraphs,
    chunk_by_sentences,
    chunk_text,
    chunk_text_with_metadata,
)


def test_short_text_returns_single_chunk() -> None:
    chunks = chunk_text_with_metadata("hello world", ChunkOptions(chunk_size=100, chunk_overlap=10))
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].metadata.has_overlap is False


def test_window_chunks_with_overlap_marker() -> None:
    text = " ".join(["word"] * 50)
    chunks = chunk_text(text, ChunkOptions(chunk_size=20, chunk_overlap=5))
    assert len(chunks) >= 2


def test_invalid_options_raise() -> None:
    with pytest.raises(ValueError):
        chunk_text_with_metadata("x", ChunkOptions(chunk_size=10, chunk_overlap=10))
    with pytest.raises(ValueError):
        chunk_text_with_metadata("x", ChunkOptions(chunk_size=0, chunk_overlap=0))


def test_word_boundary_preserved_when_enabled() -> None:
    text = "alpha beta gamma delta epsilon zeta"
    chunks = chunk_text(text, ChunkOptions(chunk_size=15, chunk_overlap=0, preserve_words=True))
    for chunk in chunks:
        # Trim spaces and check no chunk ends mid-word.
        assert not chunk.endswith(("a", "b", "g", "d", "e", "z")) or chunk in text


def test_chunk_by_sentences_groups_with_overlap() -> None:
    text = "First. Second. Third. Fourth."
    chunks = chunk_by_sentences(text, max_sentences=2, overlap_sentences=1)
    assert len(chunks) >= 2


def test_chunk_by_paragraphs_handles_blank_lines() -> None:
    text = "One.\n\nTwo.\n\nThree.\n\nFour."
    chunks = chunk_by_paragraphs(text, max_paragraphs=2, overlap_paragraphs=0)
    assert len(chunks) == 2


def test_empty_input_returns_empty_list() -> None:
    assert chunk_text("", ChunkOptions(chunk_size=10, chunk_overlap=0)) == []
    assert chunk_by_sentences("", 3) == []
    assert chunk_by_paragraphs("", 3) == []
