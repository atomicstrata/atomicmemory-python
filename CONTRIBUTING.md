# Contributing to atomicmemory-python

Thank you for helping improve the AtomicMemory Python SDK. This package mirrors
the public surface of the TypeScript SDK while using Python-native conventions,
typed Pydantic models, and `httpx` clients.

## Setup

Use `uv` for package management:

```bash
uv sync --extra dev --extra embeddings
```

Do not use `uv pip install` for repository setup.

## Development Checks

Run these before opening a pull request:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy atomicmemory --strict
uv run vulture atomicmemory tests .vulture_whitelist.py --min-confidence 90
uv run pytest
```

Integration tests are opt-in and require a live provider backend:

```bash
uv run pytest -m integration
```

## Branch Conventions

- `feat/<name>` for new features
- `fix/<name>` for bug fixes
- `docs/<name>` for documentation-only changes
- `chore/<name>` for tooling, dependency, and maintenance work

## Pull Request Checklist

- Tests or a clear validation note are included.
- Public behavior changes are documented in `README.md` or examples.
- Provider-specific behavior stays aligned with the TypeScript SDK contract.
- New code keeps files under 400 lines and functions under 40 lines, excluding comments and docstrings.
- No secrets, local credentials, or environment-specific values are committed.

## License

By contributing, you agree that your contributions will be licensed under the
same license as this repository. See [LICENSE](LICENSE).
