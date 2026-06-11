# Changelog

All notable changes to `atomicmemory` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-06-09

### Added
- `atomicmemory.contract.v1`: a wire codec for the v1 provider contract's deliberately mixed-case encoding (`Memory.createdAt`/`updatedAt` and `SearchResult.rankingScore` are camelCase on the wire; `version_id`, `observed_at`, and retrieval-receipt fields are snake_case). Encode/decode helpers cover `Memory`, `Provenance`, `SearchResult`, `SearchResultPage`, `SearchRequest`, and ingest payloads (`IngestInput`, `IngestResult`). Dates follow the contract's ISO-8601 UTC millisecond `Z` form (`_to_iso_z`, equivalent to TS `toISOString()`). Naive datetimes in encode paths are assumed UTC. `encode_ingest_input` fails closed on the Python-ahead `content_class` field (no place in the v1 `additionalProperties: false` schemas; TS contract alignment is a recorded follow-up). Explicit-null `version_id` in `SearchResult` normalizes to absent on re-encode, matching the TS optional declaration. `encode_search_request` uses `by_alias=True` so Python-keyword-safe combinator field names (`and_`/`or_`/`not_`) emit their wire aliases; a recursive `_jsonify` walk converts any `datetime` operands in filter trees to the toISOString form. In-process models and provider mappers are unchanged.
- Vendored the TS SDK's versioned v1 wire contract (JSON Schemas, cross-provider conformance corpus, and CONTRACT.md) under `contract/`, with explicit provenance in `contract/VENDORED.json` and a documented refresh script (`scripts/refresh_contract.py`, never run in CI). A pytest conformance harness proves corpus fixtures decode into the Python models (directly for snake-on-wire types, through the codec for the mixed-case search response) and that SDK emissions validate against the vendored draft-2020-12 schemas, with the TS suite's negative cases mirrored against both schemas and Pydantic. The `capabilities-descriptor` case is schema-only (no Python model in this release — recorded follow-up).
- `atomicmemory.contract` re-exports `v1` as a specialty import surface; deliberately not re-exported from the package root to keep the root namespace focused on the core provider API.
- `AsyncProviderFactory` now accepts factories that return an `Awaitable[AsyncProviderRegistration]`, enabling lazy or async provider construction during `AsyncMemoryService.initialize()`.
- `MemoryService.initialize()` and `AsyncMemoryService.initialize()` raise `ConfigError` when the configured default provider has no registered factory, making a misconfigured default an immediate, explicit error rather than a silent no-op.

### Changed
- `content_class` is now accepted on **every** ingest mode (`text`, `messages`, and `verbatim`), not just `verbatim`, and is forwarded to core for all modes. Extraction-based ingests (`text`/`messages`) can now satisfy a core running the default `RAW_CONTENT_POLICY=reject`. Still never defaulted — omitting it leaves the field off the wire and a reject-policy core fails closed.
- Both clients' `initialize()` is now concurrency-safe and idempotent: concurrent callers share a single initialization run (the first caller's registry wins), and the completed outcome — success or failure — is captured in loop-independent state for `AsyncMemoryClient`.
- A failed `initialize()` is sticky: retrying re-raises the original error from any caller; resolve the cause and construct a new client rather than retrying on the same instance.
- `AsyncMemoryClient.initialize()` shields each waiter from cancellation so that one waiter's timeout or cancellation never cancels the shared run for other concurrent callers.
- `AsyncMemoryClient.close()` during a pending initialization cancels the shared run; staged providers are torn down by the service's atomic-initialize cleanup, any concurrent `initialize()` waiter receives `CancelledError`, and the client ends in the not-initialized state without recording a sticky error.
- Both `MemoryService` and `AsyncMemoryService` stage provider registrations atomically: factories and provider `initialize()` calls run against a local staging area, and the maps are replaced only after every provider succeeds; on any failure, already-staged providers are torn down best-effort before the original error re-raises.
- `MemoryService.close()` and `AsyncMemoryService.close()` are best-effort: every provider gets a chance to close regardless of earlier failures, maps are cleared in a `finally` block, and the first failure is re-raised after all providers have been given the chance to close.

### Fixed
- `atomicmemory.__version__` reported `1.0.0` while package metadata said `1.0.1`; all version sources now agree at `1.1.0`, guarded by a regression test that will fail if they drift again.

## [1.0.1] - 2026-05-14

### Changed
- Version bump for public package publication after internal-to-public repository sync.

## [1.0.0]

Initial public stable release.

### Added
- `AtomicMemoryClient` and `AsyncAtomicMemoryClient` as the primary public client surfaces.
- Memory ingestion, search, package, get, list, and delete support.
- AtomicMemory, Mem0, and Hindsight provider adapters.
- Typed AtomicMemory namespace handles for lifecycle, audit, lessons, agents, and runtime config.
- Direct artifact storage client with pointer and managed artifact workflows.
- Local embedding, semantic search, and KV cache helpers.
- Pydantic models, typed exceptions, and `py.typed` marker for downstream type checkers.
