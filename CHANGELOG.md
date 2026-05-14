# Changelog

All notable changes to `atomicmemory` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
