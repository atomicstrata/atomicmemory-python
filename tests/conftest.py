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


@dataclass(frozen=True)
class HindsightIntegrationTestConfig:
    """Live Hindsight smoke-test environment.

    The test suite intentionally keeps this separate from the AtomicMemory core
    integration config so a developer can opt into one backend without starting
    every supported backend locally.
    """

    enabled_flag: str | None
    api_url: str | None
    api_key: str | None
    timeout_seconds: str | None
    api_version: str | None
    project_id: str | None

    @property
    def enabled(self) -> bool:
        return self.enabled_flag == "1"


@pytest.fixture(scope="session")
def integration_config() -> IntegrationTestConfig:
    return IntegrationTestConfig(
        api_url=os.environ.get("ATOMICMEMORY_TEST_API_URL"),
        api_key=os.environ.get("ATOMICMEMORY_TEST_API_KEY"),
    )


@pytest.fixture(scope="session")
def hindsight_integration_config() -> HindsightIntegrationTestConfig:
    return HindsightIntegrationTestConfig(
        enabled_flag=os.environ.get("ATOMICMEMORY_HINDSIGHT_INTEGRATION"),
        api_url=os.environ.get("HINDSIGHT_API_URL"),
        api_key=os.environ.get("HINDSIGHT_API_KEY"),
        timeout_seconds=os.environ.get("HINDSIGHT_TIMEOUT_SECONDS"),
        api_version=os.environ.get("HINDSIGHT_API_VERSION"),
        project_id=os.environ.get("HINDSIGHT_PROJECT_ID"),
    )
