"""V3 memory types.

Port of `atomicmemory-sdk/src/memory/types.ts`. Pydantic v2 models with
snake_case field names; wire-format translation (e.g. core's `user_id`
or `created_at`) lives in each provider's `mappers.py`.

The discriminated union `IngestInput` is modeled with Pydantic's
`discriminator="mode"` so callers can pass plain dicts and validation
picks the right variant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from atomicmemory.memory.filters import FieldFilterOp, FilterExpr

# ---------------------------------------------------------------------------
# Identity / partition
# ---------------------------------------------------------------------------


MessageRole = Literal["user", "assistant", "system", "tool"]
MemoryKind = Literal["fact", "episode", "summary", "procedure", "document"]
MemoryVersionEvent = Literal["created", "updated", "superseded", "invalidated"]
PackageFormat = Literal["flat", "tiered", "structured"]
IngestMode = Literal["text", "messages", "verbatim"]


class Scope(BaseModel):
    """Identity and partition context for memory operations.

    Providers declare which fields they require via
    ``capabilities().required_scope``.
    """

    model_config = ConfigDict(extra="forbid")

    user: str | None = None
    agent: str | None = None
    namespace: str | None = None
    thread: str | None = None


class MemoryRef(BaseModel):
    """Reference to a specific memory within a scope."""

    model_config = ConfigDict(extra="forbid")

    id: str
    scope: Scope


class Provenance(BaseModel):
    """Where a memory came from."""

    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    source_url: str | None = None
    source_id: str | None = None
    extractor: str | None = None


class Memory(BaseModel):
    """A single memory unit returned by get/list/search."""

    model_config = ConfigDict(extra="ignore")

    id: str
    content: str
    scope: Scope
    kind: MemoryKind | None = None
    created_at: datetime
    updated_at: datetime | None = None
    provenance: Provenance | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class IngestBase(BaseModel):
    """Common ingest fields shared by every mode."""

    model_config = ConfigDict(extra="forbid")

    scope: Scope
    provenance: Provenance | None = None
    metadata: dict[str, Any] | None = None


class TextIngest(IngestBase):
    """Raw text: conversation transcript, document, note."""

    mode: Literal["text"] = "text"
    content: str


class Message(BaseModel):
    """One turn in a structured chat conversation."""

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str
    name: str | None = None


class MessageIngest(IngestBase):
    """Structured chat messages."""

    mode: Literal["messages"] = "messages"
    messages: list[Message]


class VerbatimIngest(IngestBase):
    """Bypass LLM extraction; store the content as a single memory.

    Capability-gated — only available when
    ``capabilities().ingest_modes`` includes ``"verbatim"``.
    """

    mode: Literal["verbatim"] = "verbatim"
    content: str
    kind: MemoryKind | None = None


IngestInput = Annotated[
    TextIngest | MessageIngest | VerbatimIngest,
    Field(discriminator="mode"),
]


class IngestResult(BaseModel):
    """Per-id outcome of a single ingest call."""

    model_config = ConfigDict(extra="ignore")

    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Provider-agnostic search request."""

    model_config = ConfigDict(extra="forbid")

    query: str
    scope: Scope
    limit: int | None = None
    threshold: float | None = None
    filter: FilterExpr | None = None
    reranker: str | None = None


class SearchResult(BaseModel):
    """A single search hit.

    ``score`` is the backward-compatible composite score (provider-
    specific). Prefer the explicit ``similarity``, ``ranking_score``, and
    ``relevance`` fields when the provider exposes them.
    """

    model_config = ConfigDict(extra="ignore")

    memory: Memory
    score: float
    similarity: float | None = None
    ranking_score: float | None = None
    relevance: float | None = None


class SearchResultPage(BaseModel):
    """Paginated page of search results."""

    model_config = ConfigDict(extra="ignore")

    results: list[SearchResult] = Field(default_factory=list)
    cursor: str | None = None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class ListRequest(BaseModel):
    """Paginated list request scoped to a single user/workspace."""

    model_config = ConfigDict(extra="forbid")

    scope: Scope
    limit: int | None = None
    cursor: str | None = None
    filter: FilterExpr | None = None


class ListResultPage(BaseModel):
    """Paginated page of memories."""

    model_config = ConfigDict(extra="ignore")

    memories: list[Memory] = Field(default_factory=list)
    cursor: str | None = None


# ---------------------------------------------------------------------------
# Context packaging
# ---------------------------------------------------------------------------


class PackageRequest(SearchRequest):
    """Search request augmented with token-budget + format hints."""

    token_budget: int | None = None
    format: PackageFormat | None = None


class ContextPackage(BaseModel):
    """Injection-ready context for an AI assistant.

    Attributes:
        text: Formatted string for prompt injection.
        results: Memories that contributed to ``text`` (debugging / attribution).
        tokens: Estimated context tokens used by ``text``.
        budget_constrained: True iff the requested token budget shaped the
            package — eligible memories were omitted entirely or eligible
            richer detail (L1/L2 tier, query-term-revealing upgrades) was
            suppressed solely because the budget could not afford it.
            Quota-driven demotion (e.g. fixed-cap policy) is NOT flagged.
            Powers the v5 CLI envelope's ``meta.budget_constrained`` field.
            Uses ``StrictBool`` so non-boolean wire values raise instead
            of silently coercing.
    """

    model_config = ConfigDict(extra="ignore")

    text: str
    results: list[SearchResult] = Field(default_factory=list)
    tokens: int = 0
    budget_constrained: StrictBool


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class CapabilitiesRequiredScope(BaseModel):
    """Per-operation required-scope manifest.

    The ``list_`` field is named with a trailing underscore because
    ``list`` is a Python builtin used inside the type annotation itself
    (``list[str]``) and shadows it during forward-ref evaluation. The
    JSON wire format still uses ``"list"`` via the alias.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    default: list[str]
    ingest: list[str] | None = None
    search: list[str] | None = None
    get: list[str] | None = None
    delete: list[str] | None = None
    list_: list[str] | None = Field(default=None, alias="list")
    update: list[str] | None = None
    package: list[str] | None = None
    temporal: list[str] | None = None
    graph: list[str] | None = None
    forget: list[str] | None = None
    profile: list[str] | None = None
    reflect: list[str] | None = None
    versioning: list[str] | None = None
    batch: list[str] | None = None


class CapabilitiesExtensions(BaseModel):
    """Boolean manifest of supported V3 extensions."""

    model_config = ConfigDict(extra="forbid")

    update: bool = False
    package: bool = False
    temporal: bool = False
    graph: bool = False
    forget: bool = False
    profile: bool = False
    reflect: bool = False
    versioning: bool = False
    batch: bool = False
    health: bool = False


class CustomExtensionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str | None = None
    description: str | None = None


class Capabilities(BaseModel):
    """Provider capability surface returned by ``provider.capabilities()``."""

    model_config = ConfigDict(extra="ignore")

    ingest_modes: list[IngestMode]
    required_scope: CapabilitiesRequiredScope
    extensions: CapabilitiesExtensions
    custom_extensions: dict[str, CustomExtensionMeta] | None = None
    supported_rerankers: list[str] | None = None
    supported_filter_ops: list[FieldFilterOp] | None = None
    max_token_budget: int | None = None


# ---------------------------------------------------------------------------
# Extension-specific types
# ---------------------------------------------------------------------------


class GraphSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    scope: Scope
    limit: int | None = None
    graph_scope: Literal["nodes", "edges", "episodes"] | None = None
    reranker: str | None = None


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    label: str
    summary: str | None = None
    score: float | None = None


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    fact: str
    from_: str = Field(alias="from")
    to: str
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    score: float | None = None


class GraphResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Profile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str
    facts: list[str] | None = None
    updated_at: datetime | None = None


class Insight(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str
    confidence: float
    supporting_memory_ids: list[str] = Field(default_factory=list)


class MemoryVersion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    content: str
    created_at: datetime
    parent_id: str | None = None
    event: MemoryVersionEvent


class HealthStatus(BaseModel):
    """V3 capability-probe health response.

    Distinct from AtomicMemory's `/memories/health` runtime snapshot.
    """

    model_config = ConfigDict(extra="ignore")
    ok: bool
    latency_ms: float | None = None
    version: str | None = None
