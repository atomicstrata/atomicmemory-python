# atomicmemory-python — agent rules

Python client SDK for the AtomicMemory memory layer.

## Contributor Context

Use this file as the repo-local contributor guide. When behavior depends on
another AtomicMemory repo, rely on the published HTTP/package contract and call
out any assumption in the PR.

Before changing code, read the relevant local files first:

- `README.md` for user-facing installation and usage.
- `pyproject.toml` for supported Python versions, dependencies, and tool config.
- `atomicmemory/` for package code and `tests/` for expected behavior.

## Repository Shape

- `atomicmemory/` — typed Python package.
- `tests/` — unit and integration tests.
- `examples/` — public usage examples.
- `pyproject.toml` — package metadata and tool configuration.

## Tooling

- **Package management:** `uv sync` (NOT `uv pip install`).
- **Python interpreter:** `.venv/bin/python`. Never the global `python`.
- **HTTP:** `httpx` (sync `Client`, async `AsyncClient`).
- **Validation:** `pydantic>=2.7`. `jsonschema` only when validating against external JSON schemas.
- **Lint/format:** `ruff` (line=120). `ruff format --check .` is part of pre-commit.
- **Types:** `mypy --strict`.
- **Dead code / static health:** `vulture --min-confidence 90`. The whitelist file `.vulture_whitelist.py` MUST be included in every invocation (it allowlists Protocol-method parameter names and context-manager dunder args). Use the `[tool.vulture]` config (`uv run vulture`) or pass it explicitly: `uv run vulture atomicmemory tests .vulture_whitelist.py --min-confidence 90`. `fallow` is TypeScript-only and is not part of this repo's verification.
- **Tests:** `pytest`, `pytest-asyncio`, `pytest-mock`, `respx`. Integration tests gated behind `-m integration`.

## Code rules

- File ≤400 lines (excl. comments/docstrings); function ≤40 lines (excl. catch/finally and docstrings); test files ≤400 lines; tests ≤40 lines.
- Google-style docstrings (`Args:`, `Returns:`, `Raises:`).
- Module docstring at the top of every file. For modules that port a specific TS file, include the TS source-of-truth path (`"""Port of atomicmemory-sdk/src/.../foo.ts."""`).
- No fallback values; no `os.getenv` in business code (config flows through Pydantic models constructed at startup).
- No silent `except`. No bare `except:`.
- Greenfield code — no backwards-compat hacks, no `_` private renames for "removed" code.
- Snake_case for Python attributes; Pydantic `Field(alias="apiUrl")` aliases preserve TS camelCase wire format.
- Keep public API behavior aligned with `atomicmemory-sdk` where both SDKs expose the same concept.
- Prefer integration tests with a real HTTP path for client behavior; use mocks only for narrow transport errors.
- **Cross-cutting controls live at one chokepoint, enumerated and bypass-tested.** When a security/correctness rule must hold for *all* of a category (every config with an `api_url`, every input reaching a sink), apply it through one shared helper, not per-surface — and back it with a **reflective enumeration test** that fails when a new surface lacks it (e.g. `test_every_api_url_config_blocks_imds` discovers every `BaseModel` with an `api_url` field). Tests must exercise the **adversarial bypass** (the encoding, the key, the header), not just the canonical example, and validate against the **downstream consumer's interpretation** (the resolver, Postgres, the server), not your own parser. This is the gap that caused AGNT-PY-001's missed `EntitiesClientConfig` and numeric-IP bypass.

## Pre-commit verification

Run before opening any PR:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy atomicmemory --strict
uv run vulture atomicmemory tests .vulture_whitelist.py --min-confidence 90
uv run pytest
```

All must be green.

## Branching

- `main` is protected; commit only via PR.
- Per-phase work lands on `feat/phase-N-<slug>` branches.
