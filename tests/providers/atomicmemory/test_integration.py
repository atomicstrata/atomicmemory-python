"""Opt-in live-core integration tests for the AtomicMemory provider.

Runs only when ``ATOMICMEMORY_TEST_API_URL`` points at a running
atomicmemory-core (set ``ATOMICMEMORY_TEST_API_KEY`` if it requires auth);
skipped otherwise, so the default unit suite stays hermetic::

    ATOMICMEMORY_TEST_API_URL=http://localhost:17350 \
    ATOMICMEMORY_TEST_API_KEY=local-dev-key \
        uv run --extra dev pytest tests/providers/atomicmemory/test_integration.py

Verifies the SDK <-> core wire contract end to end against a real backend: the
audit-grade retrieval receipt and per-result version/observed fields the SDK now
surfaces are actually emitted by core and mapped through, and verbatim ingest
keyed by ``externalId`` is idempotent. Requires a core built with the
capabilities/receipt/external-id support (atomicmemory-internal PR #18).
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from atomicmemory.memory.types import Scope, SearchRequest, SearchResultPage, VerbatimIngest
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.atomicmemory.provider import AtomicMemoryProvider

_API_URL = os.environ.get("ATOMICMEMORY_TEST_API_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _API_URL, reason="Set ATOMICMEMORY_TEST_API_URL to run live-core integration tests"),
]

_SCOPE = Scope(user="sdk-itest-user")
_EXTERNAL_ID = "sdk-itest-receipt-py"
_CONTENT = "Integration probe: Northstar Atlas deploys on-prem and prioritizes low query latency."
_QUERY = "on-prem low latency Atlas"


@pytest.fixture(scope="module")
def provider() -> Generator[AtomicMemoryProvider, None, None]:
    instance = AtomicMemoryProvider(
        AtomicMemoryProviderConfig(
            api_url=_API_URL,  # type: ignore[arg-type]
            api_key=os.environ.get("ATOMICMEMORY_TEST_API_KEY"),
        )
    )
    instance.initialize()
    instance.ingest(
        VerbatimIngest(scope=_SCOPE, content=_CONTENT, content_class="summary", metadata={"externalId": _EXTERNAL_ID})
    )
    yield instance
    instance.close()


def _match_count(page: SearchResultPage) -> int:
    return sum(1 for result in page.results if result.memory.content == _CONTENT)


def test_search_surfaces_retrieval_receipt(provider: AtomicMemoryProvider) -> None:
    page = provider.search(SearchRequest(query=_QUERY, scope=_SCOPE, limit=5))

    assert page.results
    assert page.retrieval is not None
    assert page.retrieval.embedding_model
    assert page.retrieval.embedding_model_version
    assert isinstance(page.retrieval.candidate_ids, list)
    assert page.retrieval.trace_id


def test_search_hits_carry_per_result_receipt_fields(provider: AtomicMemoryProvider) -> None:
    page = provider.search(SearchRequest(query=_QUERY, scope=_SCOPE, limit=5))
    hit = page.results[0]

    assert hit.observed_at  # present on a live search hit
    # version_id is present on the model (str for a versioned row, None otherwise).
    assert hasattr(hit, "version_id")


def test_verbatim_ingest_keyed_by_external_id_is_idempotent(provider: AtomicMemoryProvider) -> None:
    before = provider.search(SearchRequest(query=_QUERY, scope=_SCOPE, limit=20))
    provider.ingest(
        VerbatimIngest(scope=_SCOPE, content=_CONTENT, content_class="summary", metadata={"externalId": _EXTERNAL_ID})
    )
    after = provider.search(SearchRequest(query=_QUERY, scope=_SCOPE, limit=20))

    assert _match_count(after) == _match_count(before) == 1
