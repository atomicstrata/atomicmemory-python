"""Real HTTP contract fixture for sync/async public memory tools."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


@dataclass
class Backend:
    """Synthetic fixture state, independent of SDK and tool implementation."""

    url: str = ""
    requests: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    status: int = 200
    ingest_response: dict[str, Any] | None = None
    hits: list[dict[str, Any]] | None = None


@pytest.fixture
def backend() -> Iterator[Backend]:
    state = Backend()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            """Keep keys and synthetic payloads out of console output."""

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
            status, result = respond(state, self.path, body)
            payload = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def respond(state: Backend, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Implement only the v1 extraction and fast-search wire contract."""
    if state.status != 200:
        return state.status, {"error": "private-backend-detail", "api_key": "test-secret"}
    user = body["user_id"]
    if path == "/v1/memories/ingest":
        if state.ingest_response is not None:
            return 201, state.ingest_response
        correction = user in state.facts
        state.facts[user] = body["conversation"]
        return 201, {
            "stored_memory_ids": [] if correction else ["mem-1"],
            "updated_memory_ids": ["mem-1"] if correction else [],
        }
    if path == "/v1/memories/search/fast":
        hits = state.hits
        if hits is None:
            hits = (
                []
                if user not in state.facts
                else [
                    {
                        "id": "mem-1",
                        "content": state.facts[user],
                        "ranking_score": 0.9,
                        "semantic_similarity": 0.8,
                        "relevance": 0.7,
                        "version_id": "v-1",
                        "observed_at": "2026-10-05T00:00:00Z",
                        "metadata": {"secret": "private"},
                    }
                ]
            )
        return 200, {
            "memories": hits,
            "count": len(hits),
            "retrieval": {
                "embedding_model": "fixture",
                "embedding_model_version": "1",
                "embedding_dimensions": 2,
                "query_text": body["query"],
                "candidate_ids": [h["id"] for h in hits],
                "trace_id": "trace-1",
            },
        }
    return 404, {"error": "unknown fixture route"}
