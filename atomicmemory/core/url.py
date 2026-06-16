"""Shared ``api_url`` validation used by every SDK config boundary.

Centralizes the rule that an ``api_url`` must be an http(s) URL with a
host, and adds SSRF defense: link-local / cloud-metadata addresses
(notably the ``169.254.169.254`` IMDS endpoint) are always rejected.
Loopback / private / reserved IP literals are *allowed by default* — the
SDK routinely connects to local and self-hosted cores — and only rejected
when the caller opts into strict mode via ``allow_private_networks=False``.
This mirrors the Node SDK's posture for cross-SDK parity.

Hostnames are intentionally NOT resolved here. Config-time DNS resolution
would be slow, racy, and still bypassable via DNS rebinding, so a literal
hostname (including ``localhost`` and ``metadata.google.internal``) passes
the scheme/host checks. Deployments that must defend against
hostname-based metadata access should pin ``api_url`` to a vetted host.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the parsed IP when ``host`` is an IP literal, else ``None``.

    Covers canonical literals AND the legacy IPv4 encodings the C resolver
    (``inet_aton``/``getaddrinfo``) still accepts — decimal (``2852039166``),
    hex (``0xA9FEA9FE``), octal (``0251.0376.0251.0376``) and short forms
    (``127.1``). Without this they slip through as un-resolved "hostnames" and
    defeat the SSRF checks, since the HTTP client resolves them to the real
    address (e.g. ``http://2852039166/`` → ``169.254.169.254``).

    Args:
        host: The URL host component.

    Returns:
        The parsed/canonicalized IP address, or ``None`` when ``host`` is a
        genuine (non-numeric) hostname.
    """
    try:
        return _collapse_mapped(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def _collapse_mapped(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Reclassify an IPv4-mapped IPv6 address (``::ffff:a.b.c.d``) as its IPv4.

    ``IPv6Address.is_link_local`` only delegates to the embedded IPv4 on
    newer CPython, so on Python 3.10/3.11 ``::ffff:169.254.169.254`` would
    otherwise read as a benign global IPv6 and bypass the metadata block.
    Collapsing to the embedded IPv4 makes classification deterministic
    across all supported interpreters and matches the Node SDK.

    Args:
        ip: A parsed IP literal.

    Returns:
        The embedded IPv4 when ``ip`` is IPv4-mapped, otherwise ``ip``.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped if mapped is not None else ip


def validate_api_url(value: str, *, allow_private_networks: bool = True) -> str:
    """Validate and normalize an ``api_url``, guarding against SSRF.

    Args:
        value: The candidate URL.
        allow_private_networks: Defaults to ``True`` — loopback / private /
            reserved IP literals are permitted because the SDK routinely
            connects to local and self-hosted cores. Pass ``False`` to reject
            those too (hardened multi-tenant deployments). Link-local /
            cloud-metadata addresses are rejected regardless of this flag.

    Returns:
        The whitespace-stripped URL.

    Raises:
        ValueError: If the scheme is not http(s), the host is missing, or
            the host is a disallowed IP literal.
    """
    stripped = value.strip()
    parsed = urlparse(stripped)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError("api_url must be an http(s) URL")
    host = parsed.hostname
    if not host:
        raise ValueError("api_url must include a host")

    ip = _parse_ip(host)
    if ip is None:
        return stripped

    if ip.is_link_local:
        raise ValueError("api_url must not target a link-local or cloud-metadata address")
    if not allow_private_networks and (
        ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    ):
        raise ValueError(
            "api_url must not target a loopback, private, or reserved address; "
            "set allow_private_networks=True to permit it"
        )
    return stripped
