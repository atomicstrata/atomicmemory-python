"""Tests for normalize_api_version."""

from __future__ import annotations

from atomicmemory.providers.atomicmemory.path import normalize_api_version


def test_v1_gets_leading_slash() -> None:
    assert normalize_api_version("v1") == "/v1"


def test_strips_leading_slashes() -> None:
    assert normalize_api_version("/v1") == "/v1"
    assert normalize_api_version("///v1") == "/v1"


def test_strips_trailing_slashes() -> None:
    assert normalize_api_version("v1/") == "/v1"
    assert normalize_api_version("v1///") == "/v1"


def test_empty_string_disables_prefix() -> None:
    assert normalize_api_version("") == ""
    assert normalize_api_version("///") == ""
