"""Regression guard: every exposed version source must agree.

pyproject.toml's `version` is what pip/uv report; `atomicmemory.__version__`
(re-exported from `_version.py`) is what runtime consumers read. They drifted
once (1.0.1 vs 1.0.0) — this test makes drift impossible to ship.
"""

from __future__ import annotations

import re
from pathlib import Path

import atomicmemory

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_sources_match() -> None:
    # Matches the first bare `version = "..."` line (column 0, MULTILINE).
    # pyproject convention puts [project].version at the top of this file and
    # no other section here declares a bare `version` key. We read the file
    # directly (not importlib.metadata) so the check is correct even in a
    # stale/unsynced environment.
    match = re.search(r'^version = "([^"]+)"$', _PYPROJECT.read_text(), re.MULTILINE)
    assert match is not None, "pyproject.toml must declare a version"
    assert match.group(1) == atomicmemory.__version__
