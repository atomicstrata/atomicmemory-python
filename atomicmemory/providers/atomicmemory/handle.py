"""AtomicMemory namespace handle — type definitions.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/handle.ts`.
Pure Pydantic models + Literal aliases for the types exposed by the
``atomicmemory.*`` extension namespace. Implementation lives in
``handle_impl.py`` and the per-category modules.

The namespace types are intentionally **not** the V3 generic types
(``Memory``, ``SearchResult``, etc.). Workspace queries must round-trip
``workspace_id`` / ``agent_id`` / ``agent_scope`` honestly, which V3's
flat ``Scope`` cannot represent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Scope (workspace discriminated union)
# ---------------------------------------------------------------------------


AgentScope = str | list[str]
"""Agent visibility scope. ``"all"|"self"|"others"`` are canonical hints;
arbitrary strings are treated as a single agent_id filter; lists are
explicit agent-id sets."""


class UserScope(BaseModel):
    """User-scoped read path — only ``user_id``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    kind: Literal["user"] = "user"
    user_id: str = Field(alias="userId")


class WorkspaceScope(BaseModel):
    """Workspace-scoped read path — full agent visibility surface."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    kind: Literal["workspace"] = "workspace"
    user_id: str = Field(alias="userId")
    workspace_id: str = Field(alias="workspaceId")
    agent_id: str = Field(alias="agentId")
    agent_scope: AgentScope | None = Field(default=None, alias="agentScope")


MemoryScope = UserScope | WorkspaceScope


# ---------------------------------------------------------------------------
# Request types — scope-free, route-shaped
# ---------------------------------------------------------------------------


Visibility = Literal["agent_only", "restricted", "workspace"]
RetrievalMode = Literal["flat", "tiered", "abstract-aware"]


class AtomicMemoryIngestInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    conversation: str
    source_site: str = Field(alias="sourceSite")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    visibility: Visibility | None = None
    config_override: dict[str, Any] | None = Field(default=None, alias="configOverride")


class AtomicMemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    query: str
    limit: int | None = None
    threshold: float | None = None
    as_of: datetime | None = Field(default=None, alias="asOf")
    retrieval_mode: RetrievalMode | None = Field(default=None, alias="retrievalMode")
    token_budget: int | None = Field(default=None, alias="tokenBudget")
    namespace_scope: str | None = Field(default=None, alias="namespaceScope")
    source_site: str | None = Field(default=None, alias="sourceSite")
    skip_repair: bool | None = Field(default=None, alias="skipRepair")
    config_override: dict[str, Any] | None = Field(default=None, alias="configOverride")


class AtomicMemoryListOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    limit: int | None = None
    offset: int | None = None
    source_site: str | None = Field(default=None, alias="sourceSite")
    episode_id: str | None = Field(default=None, alias="episodeId")


# ---------------------------------------------------------------------------
# Response: AtomicMemory-specific memory + search shapes
# ---------------------------------------------------------------------------


class AtomicMemoryMemory(BaseModel):
    """Mirrors core's memory record with full MemoryScope round-tripped."""

    model_config = ConfigDict(extra="ignore")
    id: str
    content: str
    scope: MemoryScope
    created_at: datetime
    updated_at: datetime | None = None
    importance: float | None = None
    source_site: str | None = None
    source_url: str | None = None
    episode_id: str | None = None
    visibility: Visibility | None = None
    metadata: dict[str, Any] | None = None


class AtomicMemorySearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memory: AtomicMemoryMemory
    score: float
    similarity: float | None = None
    ranking_score: float | None = None
    relevance: float | None = None
    importance: float | None = None


class TierAssignment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memory_id: str
    tier: str
    estimated_tokens: int


class LessonCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    safe: bool
    warnings: list[Any] = Field(default_factory=list)
    highest_severity: str
    matched_count: int


class ConsensusInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    original_count: int
    filtered_count: int
    removed_count: int
    removed_memory_ids: list[str] = Field(default_factory=list)


class ObservabilityInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    retrieval: Any | None = None
    packaging: Any | None = None
    assembly: Any | None = None


class AtomicMemorySearchResultPage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    count: int
    retrieval_mode: str
    scope: MemoryScope
    results: list[AtomicMemorySearchResult] = Field(default_factory=list)
    injection_text: str | None = None
    citations: list[str] | None = None
    tier_assignments: list[TierAssignment] | None = None
    expand_ids: list[str] | None = None
    estimated_context_tokens: int | None = None
    lesson_check: LessonCheck | None = None
    consensus: ConsensusInfo | None = None
    observability: ObservabilityInfo | None = None


class AtomicMemoryIngestResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    episode_id: str
    facts_extracted: int
    memories_stored: int
    memories_updated: int
    memories_deleted: int
    memories_skipped: int
    stored_memory_ids: list[str] = Field(default_factory=list)
    updated_memory_ids: list[str] = Field(default_factory=list)
    links_created: int
    composites_created: int


class AtomicMemoryListResultPage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memories: list[AtomicMemoryMemory] = Field(default_factory=list)
    count: int
    cursor: str | None = None


# ---------------------------------------------------------------------------
# Lifecycle response types
# ---------------------------------------------------------------------------


class ConsolidationScanResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memories_scanned: int
    clusters_found: int
    memories_in_clusters: int
    clusters: list[Any] = Field(default_factory=list)


class ConsolidationExecutionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    clusters_consolidated: int
    memories_archived: int
    memories_created: int
    consolidated_memory_ids: list[str] = Field(default_factory=list)


ConsolidationResult = ConsolidationScanResult | ConsolidationExecutionResult


class DecayCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    retention_score: float


class DecayResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memories_evaluated: int
    candidates_for_archival: list[DecayCandidate] = Field(default_factory=list)
    retention_threshold: float
    avg_retention_score: float
    archived: int


CapStatus = Literal["ok", "warn", "exceeded"]
CapRecommendation = Literal["none", "consolidate", "decay", "consolidate-and-decay"]


class CapCheckResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    active_memories: int
    max_memories: int
    status: CapStatus
    usage_ratio: float
    recommendation: CapRecommendation


class StatsResult(BaseModel):
    """Open-shape stats payload from core's ``GET /memories/stats``."""

    model_config = ConfigDict(extra="allow")


class ResetSourceResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    success: Literal[True] = True
    deleted_memories: int
    deleted_episodes: int


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    processed: int
    resolved: int
    noops: int
    updates: int
    supersedes: int
    deletes: int
    adds: int
    errors: int
    duration_ms: int


class ReconcileStatus(BaseModel):
    """Open-shape reconcile-status payload from core."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Audit response types
# ---------------------------------------------------------------------------


MutationType = Literal["add", "update", "supersede", "delete", "clarify"]


class MutationSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_versions: int
    active_versions: int
    superseded_versions: int
    total_claims: int
    by_mutation_type: dict[str, int] = Field(default_factory=dict)


class MutationRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    claim_id: str
    user_id: str
    memory_id: str | None
    content: str
    mutation_type: MutationType | None
    mutation_reason: str | None
    actor_model: str | None
    contradiction_confidence: float | None
    previous_version_id: str | None
    superseded_by_version_id: str | None
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime


class RecentMutationsResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mutations: list[MutationRecord] = Field(default_factory=list)
    count: int


class AuditTrailEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version_id: str
    claim_id: str
    content: str
    mutation_type: MutationType | None
    mutation_reason: str | None
    actor_model: str | None
    contradiction_confidence: float | None
    previous_version_id: str | None
    superseded_by_version_id: str | None
    valid_from: datetime
    valid_to: datetime | None
    memory_id: str | None


class AuditTrailResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memory_id: str
    trail: list[AuditTrailEntry] = Field(default_factory=list)
    version_count: int


# ---------------------------------------------------------------------------
# Lessons response types
# ---------------------------------------------------------------------------


LessonType = Literal[
    "injection_blocked",
    "false_memory",
    "contradiction_pattern",
    "user_reported",
    "consensus_violation",
    "trust_violation",
]
LessonSeverity = Literal["low", "medium", "high", "critical"]


class Lesson(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    lesson_type: LessonType
    pattern: str
    embedding: list[float] = Field(default_factory=list)
    source_memory_ids: list[str] = Field(default_factory=list)
    source_query: str | None
    severity: LessonSeverity
    active: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class LessonsListResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lessons: list[Lesson] = Field(default_factory=list)
    count: int


class LessonStats(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_active: int
    by_type: dict[str, int] = Field(default_factory=dict)


class ReportLessonResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lesson_id: str


# ---------------------------------------------------------------------------
# Config response + request types
# ---------------------------------------------------------------------------


EmbeddingProviderName = Literal["openai", "ollama", "openai-compatible", "transformers"]
LLMProviderName = Literal[
    "openai",
    "ollama",
    "openai-compatible",
    "transformers",
    "groq",
    "anthropic",
    "google-genai",
]


class HealthConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    retrieval_profile: str
    embedding_provider: EmbeddingProviderName
    embedding_model: str
    llm_provider: LLMProviderName
    llm_model: str
    clarification_conflict_threshold: float
    max_search_results: int
    hybrid_search_enabled: bool
    iterative_retrieval_enabled: bool
    entity_graph_enabled: bool
    cross_encoder_enabled: bool
    agentic_retrieval_enabled: bool
    repair_loop_enabled: bool


class AtomicMemoryHealthStatus(BaseModel):
    """Distinct from V3's ``HealthStatus`` (capability probe).

    Mirrors core's ``GET /memories/health`` runtime snapshot.
    """

    model_config = ConfigDict(extra="ignore")
    status: Literal["ok"] = "ok"
    config: HealthConfig


class ConfigUpdates(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    similarity_threshold: float | None = Field(default=None, alias="similarityThreshold")
    audn_candidate_threshold: float | None = Field(default=None, alias="audnCandidateThreshold")
    clarification_conflict_threshold: float | None = Field(default=None, alias="clarificationConflictThreshold")
    max_search_results: int | None = Field(default=None, alias="maxSearchResults")


class ConfigUpdateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    applied: list[str] = Field(default_factory=list)
    config: HealthConfig
    note: str


# ---------------------------------------------------------------------------
# Agents response types
# ---------------------------------------------------------------------------


ConflictResolution = Literal["resolved_new", "resolved_existing", "resolved_both"]
ConflictStatus = Literal["open", "resolved_new", "resolved_existing", "resolved_both", "auto_resolved"]


class SetTrustResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agent_id: str
    trust_level: float


class GetTrustResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agent_id: str
    trust_level: float


class AgentConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    new_memory_id: str | None
    existing_memory_id: str | None
    new_agent_id: str | None
    existing_agent_id: str | None
    new_trust_level: float | None
    existing_trust_level: float | None
    contradiction_confidence: float
    clarification_note: str | None
    status: ConflictStatus
    resolution_policy: str | None
    resolved_at: datetime | None
    created_at: datetime
    auto_resolve_after: datetime | None


class ConflictsListResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    conflicts: list[AgentConflict] = Field(default_factory=list)
    count: int


class ResolveConflictResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    status: ConflictResolution


class AutoResolveConflictsResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resolved: int


ATOMICMEMORY_EXTENSION_NAMES: tuple[str, ...] = (
    "atomicmemory.base",
    "atomicmemory.lifecycle",
    "atomicmemory.audit",
    "atomicmemory.lessons",
    "atomicmemory.config",
    "atomicmemory.agents",
)
