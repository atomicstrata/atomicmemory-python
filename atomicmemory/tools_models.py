"""Validated tool arguments and bounded, allowlisted retrieval output."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from atomicmemory.memory.types import RetrievalReceipt, SearchResultPage

MAX_USER_LENGTH = 256
MAX_QUERY_LENGTH = 4096
MAX_CONTENT_LENGTH = 32768
MAX_SEARCH_LIMIT = 20
MAX_HIT_CONTENT = 4096
MAX_TOTAL_CONTENT = 16384


class ToolScope(BaseModel):
    """Trusted configuration, excluded from the model's argument schemas."""

    model_config = ConfigDict(extra="forbid", strict=True)
    user: str = Field(min_length=1, max_length=MAX_USER_LENGTH)

    @field_validator("user")
    @classmethod
    def validate_user(cls, value: str) -> str:
        """Refuse blank users and project-wide Cloud identities."""
        if not value.strip() or value.strip().startswith("project:"):
            raise ValueError("Invalid user")
        return value


class IngestArguments(BaseModel):
    """Model-controlled ingest arguments; no endpoint, identity, or metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Refuse whitespace-only input without changing saved text."""
        if not value.strip():
            raise ValueError("Blank content")
        return value


class SearchArguments(BaseModel):
    """Model-controlled search arguments with the TypeScript tool limits."""

    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    limit: int = Field(default=5, ge=1, le=MAX_SEARCH_LIMIT)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Refuse whitespace-only queries."""
        if not value.strip():
            raise ValueError("Blank query")
        return value


class MemorySearchHit(BaseModel):
    """Search evidence without backend metadata, provenance, or scope fields."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    id: str = Field(min_length=1)
    content: str
    score: float
    truncated: bool
    similarity: float | None = None
    ranking_score: float | None = None
    relevance: float | None = None
    version_id: str | None = None
    observed_at: str | None = None


class MemorySearchOutput(BaseModel):
    """Bounded hits and the backend's original retrieval evidence."""

    results: list[MemorySearchHit]
    truncated: bool
    retrieval: RetrievalReceipt | None = None
    cursor: str | None = None


def project_search(page: SearchResultPage, limit: int) -> MemorySearchOutput:
    """Bound model-facing hit count and text while retaining score/version evidence."""
    remaining = MAX_TOTAL_CONTENT
    results: list[MemorySearchHit] = []
    for hit in page.results[:limit]:
        content = hit.memory.content[: min(MAX_HIT_CONTENT, remaining)]
        remaining -= len(content)
        results.append(
            MemorySearchHit(
                id=hit.memory.id,
                content=content,
                score=hit.score,
                truncated=len(content) < len(hit.memory.content),
                similarity=hit.similarity,
                ranking_score=hit.ranking_score,
                relevance=hit.relevance,
                version_id=hit.version_id,
                observed_at=hit.observed_at,
            )
        )
    return MemorySearchOutput(
        results=results,
        truncated=len(page.results) > len(results) or any(hit.truncated for hit in results),
        retrieval=page.retrieval,
        cursor=page.cursor,
    )
