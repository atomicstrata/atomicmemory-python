"""Text chunking helpers.

Port of `atomicmemory-sdk/src/utils/chunking.ts`. Three strategies:

- :func:`chunk_text_with_metadata` — character-window with optional
  word-boundary preservation and overlap.
- :func:`chunk_by_sentences` — split on ``.!?`` then re-group with
  overlap.
- :func:`chunk_by_paragraphs` — split on blank lines then re-group with
  overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkOptions:
    """Configuration for :func:`chunk_text_with_metadata`."""

    chunk_size: int
    chunk_overlap: int
    preserve_words: bool = True
    separator: str = " "
    min_chunk_size: int | None = None


@dataclass(frozen=True)
class ChunkMetadata:
    word_count: int
    char_count: int
    has_overlap: bool


@dataclass(frozen=True)
class ChunkResult:
    text: str
    index: int
    start_offset: int
    end_offset: int
    metadata: ChunkMetadata


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text) if w])


def _validate(options: ChunkOptions) -> int:
    if options.chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if options.chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if options.chunk_overlap >= options.chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")
    raw_min = options.min_chunk_size if options.min_chunk_size is not None else max(1, options.chunk_size // 10)
    return max(1, min(raw_min, options.chunk_size))


def chunk_text(text: str, options: ChunkOptions) -> list[str]:
    """Return chunks as plain strings; thin wrapper around metadata variant."""
    return [c.text for c in chunk_text_with_metadata(text, options)]


def chunk_text_with_metadata(text: str, options: ChunkOptions) -> list[ChunkResult]:
    """Sliding-window chunker with optional word-boundary preservation."""
    if not isinstance(text, str) or text == "":
        return []
    min_chunk_size = _validate(options)
    if len(text) <= options.chunk_size:
        trimmed = text.strip()
        return [
            ChunkResult(
                text=trimmed,
                index=0,
                start_offset=0,
                end_offset=len(text),
                metadata=ChunkMetadata(
                    word_count=_word_count(trimmed),
                    char_count=len(text),
                    has_overlap=False,
                ),
            )
        ]
    return _chunk_window(text, options, min_chunk_size)


def _chunk_window(text: str, options: ChunkOptions, min_chunk_size: int) -> list[ChunkResult]:
    chunks: list[ChunkResult] = []
    current_offset = 0
    chunk_index = 0
    while current_offset < len(text):
        end_offset = min(current_offset + options.chunk_size, len(text))
        chunk_text_slice = text[current_offset:end_offset]
        if options.preserve_words and end_offset < len(text):
            last_sep = chunk_text_slice.rfind(options.separator)
            if last_sep > min_chunk_size:
                end_offset = current_offset + last_sep
                chunk_text_slice = text[current_offset:end_offset]
        trimmed = chunk_text_slice.strip()
        if len(trimmed) >= min_chunk_size:
            chunks.append(
                ChunkResult(
                    text=trimmed,
                    index=chunk_index,
                    start_offset=current_offset,
                    end_offset=end_offset,
                    metadata=ChunkMetadata(
                        word_count=_word_count(trimmed),
                        char_count=len(trimmed),
                        has_overlap=chunk_index > 0,
                    ),
                )
            )
            chunk_index += 1
        next_offset = end_offset - options.chunk_overlap
        current_offset = end_offset if next_offset <= current_offset else next_offset
        if end_offset >= len(text):
            break
    return chunks


def chunk_by_sentences(text: str, max_sentences: int, overlap_sentences: int = 1) -> list[str]:
    """Group sentences with overlap; sentence boundary = ``[.!?]+``."""
    if not isinstance(text, str) or text == "":
        return []
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) <= max_sentences:
        return [text]
    chunks: list[str] = []
    current = 0
    while current < len(sentences):
        end = min(current + max_sentences, len(sentences))
        slice_ = sentences[current:end]
        if slice_:
            chunks.append(". ".join(slice_) + ".")
        current = end - overlap_sentences
        if current <= 0 or end >= len(sentences):
            break
    return chunks


def chunk_by_paragraphs(text: str, max_paragraphs: int, overlap_paragraphs: int = 0) -> list[str]:
    """Group paragraphs with overlap; paragraph boundary = blank lines."""
    if not isinstance(text, str) or text == "":
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= max_paragraphs:
        return [text]
    chunks: list[str] = []
    current = 0
    while current < len(paragraphs):
        end = min(current + max_paragraphs, len(paragraphs))
        slice_ = paragraphs[current:end]
        if slice_:
            chunks.append("\n\n".join(slice_))
        current = end - overlap_paragraphs
        if current <= 0 or end >= len(paragraphs):
            break
    return chunks
