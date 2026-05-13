"""pytest configuration shared across the test tree.

Sets up the integration test config model and registers any
provider-agnostic fixtures.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class IntegrationTestConfig:
    """Single source of truth for integration test environment.

    Reads `ATOMICMEMORY_TEST_API_URL` once at session start so per-test
    code doesn't scatter `os.getenv` calls.
    """

    api_url: str | None
    api_key: str | None

    @property
    def enabled(self) -> bool:
        return self.api_url is not None


@pytest.fixture(scope="session")
def integration_config() -> IntegrationTestConfig:
    return IntegrationTestConfig(
        api_url=os.environ.get("ATOMICMEMORY_TEST_API_URL"),
        api_key=os.environ.get("ATOMICMEMORY_TEST_API_KEY"),
    )
