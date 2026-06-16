"""Tests for the shared ``api_url`` SSRF guard.

Verifies that :func:`atomicmemory.core.url.validate_api_url` enforces an
http(s) scheme, always rejects link-local / cloud-metadata addresses
(e.g. the AWS IMDS endpoint) even when private networks are permitted,
and gates loopback / private / reserved IPs behind the explicit
``allow_private_networks`` opt-in. Hostnames are intentionally not
DNS-resolved at config time.
"""

from __future__ import annotations

import pytest

from atomicmemory.core.url import validate_api_url


def test_allows_public_http_and_https() -> None:
    assert validate_api_url("https://api.example.com") == "https://api.example.com"
    assert validate_api_url("http://core.test:17350") == "http://core.test:17350"


def test_allows_hostnames_without_dns_resolution() -> None:
    # Literal hostnames (incl. localhost) are not resolved at config time.
    assert validate_api_url("http://localhost:17350") == "http://localhost:17350"


@pytest.mark.parametrize("bad", ["not-a-url", "ftp://host/x", "file:///etc/passwd", "://no-scheme"])
def test_rejects_non_http_scheme_or_missing_host(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_api_url(bad)


@pytest.mark.parametrize(
    "metadata_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[fe80::1]/x",
    ],
)
def test_always_rejects_link_local_even_when_private_allowed(metadata_url: str) -> None:
    with pytest.raises(ValueError):
        validate_api_url(metadata_url, allow_private_networks=True)


@pytest.mark.parametrize(
    "private_url",
    [
        "http://127.0.0.1:17350",
        "http://10.0.0.5/api",
        "http://192.168.1.10:8080",
        "http://172.16.0.1/x",
        "http://[::1]:17350",
    ],
)
def test_allows_private_and_loopback_ips_by_default(private_url: str) -> None:
    # Posture B: the SDK connects to local/self-hosted cores, so these pass.
    assert validate_api_url(private_url) == private_url


@pytest.mark.parametrize(
    "private_url",
    [
        "http://127.0.0.1:17350",
        "http://10.0.0.5/api",
        "http://172.16.0.1/x",
        "http://[::1]:17350",
    ],
)
def test_rejects_private_and_loopback_ips_when_strict(private_url: str) -> None:
    with pytest.raises(ValueError):
        validate_api_url(private_url, allow_private_networks=False)


@pytest.mark.parametrize(
    "mapped_imds",
    ["http://[::ffff:169.254.169.254]/", "http://[::ffff:a9fe:a9fe]/"],
)
def test_rejects_ipv4_mapped_ipv6_metadata(mapped_imds: str) -> None:
    # ::ffff:169.254.169.254 collapses to the embedded IPv4 and stays blocked
    # even with private networks allowed (cross-Python determinism).
    with pytest.raises(ValueError):
        validate_api_url(mapped_imds, allow_private_networks=True)


def test_strips_surrounding_whitespace() -> None:
    assert validate_api_url("  https://api.example.com  ") == "https://api.example.com"


@pytest.mark.parametrize(
    "encoded_imds",
    [
        "http://2852039166/latest/meta-data/",  # decimal 169.254.169.254
        "http://0xA9FEA9FE/",  # hex 169.254.169.254
        "http://0251.0376.0251.0376/",  # dotted-octal 169.254.169.254
    ],
)
def test_rejects_numeric_encoded_metadata_address(encoded_imds: str) -> None:
    # Legacy IPv4 encodings the resolver still accepts must not bypass the
    # always-on link-local/metadata block (even with private networks allowed).
    with pytest.raises(ValueError):
        validate_api_url(encoded_imds, allow_private_networks=True)


@pytest.mark.parametrize(
    "encoded_private",
    [
        "http://2130706433:17350/",  # decimal 127.0.0.1
        "http://0x7f000001/",  # hex loopback
        "http://127.1/",  # short-form loopback
        "http://0/",  # 0.0.0.0 (unspecified)
    ],
)
def test_rejects_numeric_encoded_private_when_strict(encoded_private: str) -> None:
    # Posture B allows these by default (loopback/unspecified are local cores);
    # strict mode must still reject them, encoding notwithstanding.
    assert validate_api_url(encoded_private) == encoded_private
    with pytest.raises(ValueError):
        validate_api_url(encoded_private, allow_private_networks=False)
