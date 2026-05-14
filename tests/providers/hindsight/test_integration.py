"""Opt-in live smoke tests for the Hindsight provider.

These tests require a running Hindsight backend with its own model configured.
They are skipped by default so ordinary SDK development never installs or
starts provider backends implicitly.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest

from atomicmemory.memory.types import Scope, SearchRequest, TextIngest
from atomicmemory.providers.hindsight.config import (
    HindsightOperation,
    HindsightOperationsHandle,
    HindsightProviderConfig,
    HindsightRetainHandle,
    HindsightRetainResponse,
)
from atomicmemory.providers.hindsight.provider import HindsightProvider
from tests.conftest import HindsightIntegrationTestConfig

pytestmark = pytest.mark.integration

COMPLETED_OPERATION_STATUSES = {"completed", "succeeded", "success"}
FAILED_OPERATION_STATUSES = {"cancelled", "canceled", "failed", "errored", "error", "timed_out", "timeout"}
OPERATION_STATUS_ATTEMPTS = 120


@pytest.fixture
def live_hindsight_provider(
    hindsight_integration_config: HindsightIntegrationTestConfig,
) -> Generator[HindsightProvider]:
    if not hindsight_integration_config.enabled:
        pytest.skip("Set ATOMICMEMORY_HINDSIGHT_INTEGRATION=1 to run live Hindsight tests")
    if not hindsight_integration_config.api_url:
        pytest.skip("Set HINDSIGHT_API_URL to run live Hindsight tests")

    provider = HindsightProvider(_provider_config(hindsight_integration_config))
    provider.initialize()
    health = provider.health()
    if not health.ok:
        provider.close()
        pytest.skip(f"Hindsight health check failed at {hindsight_integration_config.api_url}")

    yield provider
    provider.close()


def test_live_retain_search_and_reflect(live_hindsight_provider: HindsightProvider) -> None:
    scope = Scope(user=f"python-sdk-{uuid4().hex}", agent="hindsight-integration")
    marker = f"python-hindsight-marker-{uuid4().hex}"
    retain = live_hindsight_provider.get_extension("hindsight.retain")
    operations = live_hindsight_provider.get_extension("hindsight.operations")

    assert isinstance(retain, HindsightRetainHandle)
    assert isinstance(operations, HindsightOperationsHandle)

    retained = retain.retain(
        TextIngest(
            content=f"The integration marker is {marker}. Preserve this marker for recall.",
            scope=scope,
        )
    )
    assert retained.success is not False
    _wait_for_retain_operations(operations, scope, retained)

    page = live_hindsight_provider.search(SearchRequest(query=marker, scope=scope, limit=3))
    insights = live_hindsight_provider.reflect("What is the integration marker?", scope)

    assert page.results
    assert insights
    assert insights[0].content


def _provider_config(raw_config: HindsightIntegrationTestConfig) -> HindsightProviderConfig:
    config: dict[str, object] = {"api_url": raw_config.api_url}
    if raw_config.api_key:
        config["api_key"] = raw_config.api_key
    if raw_config.timeout_seconds:
        config["timeout_seconds"] = raw_config.timeout_seconds
    if raw_config.api_version:
        config["api_version"] = raw_config.api_version
    if raw_config.project_id:
        config["project_id"] = raw_config.project_id
    return HindsightProviderConfig.model_validate(config)


def _wait_for_retain_operations(
    operations: HindsightOperationsHandle,
    scope: Scope,
    retained: HindsightRetainResponse,
) -> None:
    operation_ids = _retain_operation_ids(retained)
    if not operation_ids and retained.async_ is False:
        return
    assert operation_ids, "Async Hindsight retain response must include operation_id or operation_ids"
    for operation_id in operation_ids:
        _wait_for_operation(operations, scope, operation_id)


def _wait_for_operation(operations: HindsightOperationsHandle, scope: Scope, operation_id: str) -> None:
    last_operation: HindsightOperation | None = None
    for _ in range(OPERATION_STATUS_ATTEMPTS):
        last_operation = operations.get(scope, operation_id)
        status = last_operation.status if last_operation else None
        if status in COMPLETED_OPERATION_STATUSES:
            return
        if status in FAILED_OPERATION_STATUSES:
            pytest.fail(f"Hindsight operation {operation_id} failed with status={status}")

    status = last_operation.status if last_operation else "missing"
    pytest.fail(f"Hindsight operation {operation_id} did not complete after polling; last status={status}")


def _retain_operation_ids(retained: HindsightRetainResponse) -> list[str]:
    operation_ids: list[str] = []
    if retained.operation_id:
        operation_ids.append(retained.operation_id)
    if retained.operation_ids:
        operation_ids.extend(
            operation_id for operation_id in retained.operation_ids if operation_id not in operation_ids
        )
    return operation_ids
