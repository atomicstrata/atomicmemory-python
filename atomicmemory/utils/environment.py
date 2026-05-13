"""Environment introspection helpers.

Port of `atomicmemory-sdk/src/utils/environment.ts`. Used internally to
gate noisy diagnostics and skip optional behavior in tests.
"""

from __future__ import annotations

import os
import sys


def is_test_environment() -> bool:
    """Return True when the SDK is running under pytest or `PYTEST_*`.

    The check is deliberately heuristic — it asks "is pytest the entry
    point" by inspecting `sys.modules` and `os.environ`. Callers must not
    use this for security-sensitive branches; it exists only to silence
    diagnostics that would otherwise spam test output.
    """
    if "pytest" in sys.modules:
        return True
    return "PYTEST_CURRENT_TEST" in os.environ
