"""Tests that 2xx responses with invalid JSON or malformed payloads raise EntitiesClientError.

Ensures no raw JSONDecodeError, ValidationError, or AttributeError escapes the sync
EntitiesClient.  Each test asserts error_code == "invalid_entities_response".
"""

from __future__ import annotations

import httpx
import pytest
import respx

from atomicmemory.entities.client import EntitiesClient
from atomicmemory.entities.errors import EntitiesClientError

_BASE_URL = "https://api.test"
_API_KEY = "test-key"


def _client() -> EntitiesClient:
    return EntitiesClient({"apiUrl": _BASE_URL, "apiKey": _API_KEY})


# ---------------------------------------------------------------------------
# profile — non-JSON body
# ---------------------------------------------------------------------------


@respx.mock
def test_profile_non_json_body_raises_invalid_entities_response() -> None:
    """profile() 200 with non-JSON body raises EntitiesClientError, not JSONDecodeError."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice/profile").mock(
        return_value=httpx.Response(200, content=b"not json at all")
    )
    with pytest.raises(EntitiesClientError) as exc_info:
        _client().profile("alice")
    assert exc_info.value.error_code == "invalid_entities_response"


# ---------------------------------------------------------------------------
# list — wrong shape (entities is a string, not a list)
# ---------------------------------------------------------------------------


@respx.mock
def test_list_wrong_shape_raises_invalid_entities_response() -> None:
    """list() 200 with wrong-shape payload raises EntitiesClientError, not ValidationError."""
    respx.get(f"{_BASE_URL}/v1/entities").mock(
        return_value=httpx.Response(200, json={"entities": "nope", "total": 0, "page": 1, "page_size": 20})
    )
    with pytest.raises(EntitiesClientError) as exc_info:
        _client().list()
    assert exc_info.value.error_code == "invalid_entities_response"


# ---------------------------------------------------------------------------
# list — response is not a JSON object (array at top level)
# ---------------------------------------------------------------------------


@respx.mock
def test_list_non_object_response_raises_invalid_entities_response() -> None:
    """list() 200 where body is a JSON array (not object) raises EntitiesClientError."""
    respx.get(f"{_BASE_URL}/v1/entities").mock(return_value=httpx.Response(200, json=[{"entity_id": "alice"}]))
    with pytest.raises(EntitiesClientError) as exc_info:
        _client().list()
    assert exc_info.value.error_code == "invalid_entities_response"


# ---------------------------------------------------------------------------
# attributes — envelope body is not a JSON object
# ---------------------------------------------------------------------------


@respx.mock
def test_attributes_non_object_envelope_raises_invalid_entities_response() -> None:
    """attributes() 200 where body is a JSON array raises EntitiesClientError."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice/attributes").mock(
        return_value=httpx.Response(200, json=[{"entity": "alice", "attribute": "role"}])
    )
    with pytest.raises(EntitiesClientError) as exc_info:
        _client().attributes("alice")
    assert exc_info.value.error_code == "invalid_entities_response"


# ---------------------------------------------------------------------------
# attributes — 'attributes' key present but value is not a list
# ---------------------------------------------------------------------------


@respx.mock
def test_attributes_non_list_value_raises_invalid_entities_response() -> None:
    """attributes() 200 where 'attributes' value is not a list raises EntitiesClientError."""
    respx.get(f"{_BASE_URL}/v1/entities/user/alice/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": "not-a-list"})
    )
    with pytest.raises(EntitiesClientError) as exc_info:
        _client().attributes("alice")
    assert exc_info.value.error_code == "invalid_entities_response"


# ---------------------------------------------------------------------------
# patch_settings — invalid JSON payload
# ---------------------------------------------------------------------------


@respx.mock
def test_patch_settings_non_json_body_raises_invalid_entities_response() -> None:
    """patch_settings() 200 with non-JSON body raises EntitiesClientError."""
    respx.patch(f"{_BASE_URL}/v1/entities/user/alice/settings").mock(
        return_value=httpx.Response(200, content=b"<html>error</html>")
    )
    with pytest.raises(EntitiesClientError) as exc_info:
        _client().patch_settings("alice", extraction_prompt="x")
    assert exc_info.value.error_code == "invalid_entities_response"
