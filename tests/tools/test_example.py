"""Run the copied public example in separate processes against the HTTP fixture."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.tools.conftest import Backend

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "memory_tools.py"


def run_example(backend: Backend, operation: str, text: str, use_async: bool) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ATOMICMEMORY_API_URL": backend.url,
        "ATOMICMEMORY_API_KEY": "test-secret",
        "ATOMICMEMORY_USER": "example-user",
    }
    command = [sys.executable, str(EXAMPLE), operation, text]
    if use_async:
        command.append("--async")
    return subprocess.run(command, env=env, text=True, capture_output=True, timeout=30, check=False)


@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
def test_example_persists_across_processes_and_shows_correction(backend, use_async):
    saved = run_example(backend, "ingest", "I prefer tea.", use_async)
    assert saved.returncode == 0, saved.stderr
    assert json.loads(saved.stdout)["created"] == ["mem-1"]
    recalled = run_example(backend, "search", "drink", use_async)
    assert recalled.returncode == 0, recalled.stderr
    assert json.loads(recalled.stdout)["results"][0]["content"] == "I prefer tea."
    corrected = run_example(backend, "ingest", "I now prefer coffee.", use_async)
    assert corrected.returncode == 0, corrected.stderr
    assert json.loads(corrected.stdout)["updated"] == ["mem-1"]
    final = run_example(backend, "search", "drink", use_async)
    assert final.returncode == 0, final.stderr
    assert json.loads(final.stdout)["results"][0]["content"] == "I now prefer coffee."


@pytest.mark.parametrize("status", [202, 401, 503])
@pytest.mark.parametrize("use_async", [False, True])
def test_example_exits_without_retry_or_leaking_backend_errors(backend, use_async, status):
    backend.status = status
    result = run_example(backend, "ingest", "Synthetic fact", use_async)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "Memory tool failed." in result.stderr
    assert "test-secret" not in result.stderr
    assert "private-backend-detail" not in result.stderr
    assert len(backend.requests) == 1
