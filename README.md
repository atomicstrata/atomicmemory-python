# atomicmemory-python

Python client SDK for [AtomicMemory](https://github.com/atomicstrata) memory and artifact storage.

A backend-agnostic memory and storage client: ingest conversations and documents, search them semantically, package retrieval-ready context, register or upload raw artifacts, and access AtomicMemory-specific features (lifecycle, audit, lessons, agents/trust, runtime config) through typed namespace handles.

This is a Python port of the TypeScript [`atomicmemory-sdk`](https://github.com/atomicstrata/atomicmemory-sdk). It mirrors the public surface 1:1 while staying idiomatic to Python (Pydantic models, `httpx` sync + async clients, `match` statements, `snake_case`).

## Status

Stable release — `1.0.0` on [PyPI](https://pypi.org/project/atomicmemory/).

## Quick start

```python
from atomicmemory import AtomicMemoryClient

with AtomicMemoryClient({
    "apiUrl": "http://localhost:3050",
    "apiKey": "server-api-key",
    "userId": "demo",
}) as client:
    client.memory.initialize()

    client.memory.ingest({
        "mode": "messages",
        "messages": [
            {"role": "user", "content": "I prefer aisle seats on flights."},
        ],
        "scope": {"user": "demo"},
    })

    page = client.memory.search({"query": "seat preference", "scope": {"user": "demo"}})
    for hit in page.results:
        print(hit.memory.content, hit.score)

    artifact = client.storage.put({
        "mode": "pointer",
        "uri": "https://example.com/manual.pdf",
        "contentType": "application/pdf",
    })
    print(artifact.artifact_id)
```

## Async usage

```python
import asyncio
from atomicmemory import AsyncAtomicMemoryClient

async def main() -> None:
    async with AsyncAtomicMemoryClient({
        "apiUrl": "http://localhost:3050",
        "apiKey": "server-api-key",
        "userId": "demo",
    }) as client:
        await client.memory.initialize()
        results = await client.memory.search({"query": "seat preference", "scope": {"user": "demo"}})
        for hit in results.results:
            print(hit.memory.content)

asyncio.run(main())
```

## AtomicMemory-specific features

When configured with the `atomicmemory` provider, the client exposes a typed handle for backend-specific routes:

```python
trail = client.memory.atomicmemory.audit.trail(memory_id="mem-123", user_id="demo")
health = client.memory.atomicmemory.config.health()
```

Categories: `lifecycle`, `audit`, `lessons`, `config`, `agents`.

## Artifact storage

The `client.storage` namespace mirrors the TypeScript SDK's direct storage API:

- `capabilities()` reports active backend support.
- `put({"mode": "pointer", ...})` registers a pointer to caller-owned bytes.
- `put({"mode": "managed", "body": b"...", ...})` uploads known-length bytes to the configured raw content store.
- `get`, `get_content`, `head`, `delete`, and `verify` address artifacts by `artifact_id`.
- `stream_content` streams large artifact bodies without buffering the entire response in memory.

Every storage request sends `Authorization: Bearer <apiKey>` and `X-AtomicMemory-User-Id`. The SDK never sends the legacy `?user_id=` URL parameter.

## Installation

```bash
pip install atomicmemory                    # core + local search + SQLite store
pip install 'atomicmemory[embeddings]'      # + sentence-transformers for local embeddings
```

## Development

```bash
uv sync --extra dev --extra embeddings
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy atomicmemory --strict
uv run vulture atomicmemory tests .vulture_whitelist.py --min-confidence 90
```

## License

MIT
