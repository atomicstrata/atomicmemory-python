# AtomicMemory Python Roadmap

This roadmap is directional. It describes the areas the maintainers are actively investing in, but it is not a promise of specific features or dates.

AtomicMemory Python is the Python client SDK for AtomicMemory. The near-term focus is a typed, reliable Python interface that tracks the core memory API and fits naturally into Python agent, service, and evaluation workflows.

## Current Focus

- Keep Python client behavior aligned with AtomicMemory Core and the TypeScript SDK where appropriate.
- Provide clear typed models for memory capture, retrieval, mutation, and result metadata.
- Support practical synchronous and asynchronous usage patterns.
- Make configuration, errors, and examples straightforward for Python developers.
- Build out tests that protect compatibility across supported Python versions.
- Prepare the repository for public contribution and package distribution.

## Near-Term Work

### API Parity

- Track the stable Core API surface for capture, search, retrieval, and memory mutation.
- Document where Python intentionally differs from the TypeScript SDK because of language conventions.
- Add migration notes when client behavior changes.
- Keep examples in sync with the docs site.

### Typed Client Experience

- Use Pydantic models for request and response shapes.
- Use httpx for transport behavior.
- Improve validation and error messages for configuration and API failures.
- Add examples for common service and notebook-style workflows.

### Async And Runtime Support

- Support async-first agent and service workflows.
- Keep synchronous usage ergonomic for scripts and simple applications.
- Verify behavior across the supported Python version matrix.
- Document connection, timeout, and retry expectations.

### Packaging And Release Readiness

- Keep package metadata, license, security policy, and contribution docs complete.
- Add badges for release, license, tests, and docs where appropriate.
- Publish clear quickstarts and minimal examples.
- Keep changelog and release notes useful for downstream users.

## Later Work

- Higher-level helper functions for context packaging and retrieval diagnostics.
- Additional examples for agent frameworks and evaluation workflows.
- Provider-specific convenience integrations where they do not weaken the core client API.
- More structured memory tools for temporal, correction-aware, and multi-session workflows.

## Contribution Areas

Good first areas for contributors include:

- Typed model improvements and docstring updates.
- Examples for common Python frameworks and agent use cases.
- Tests for client behavior across Python versions.
- Bug reports with request, response, and environment details.
- Documentation fixes that make setup or usage clearer.

## Non-Goals

- The Python SDK should not become a separate memory engine with behavior that diverges from Core.
- The Python SDK should not require a hosted AtomicMemory service.
- The Python SDK should not expose internal benchmark strategy, private launch plans, or customer-specific work.
- The Python SDK should not introduce hidden fallback behavior that masks configuration errors.

## How We Prioritize

We prioritize correctness, type clarity, API parity, and examples that help Python developers build real memory-enabled applications without guessing at the underlying Core behavior.
