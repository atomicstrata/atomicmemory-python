"""Route-path helpers for the AtomicMemory provider.

Port of `atomicmemory-sdk/src/memory/atomicmemory-provider/path.ts`.
"""

from __future__ import annotations


def normalize_api_version(api_version: str) -> str:
    """Normalize a config value to a leading-slash prefix, no trailing slash.

    Examples:
        ``"v1"`` → ``"/v1"``
        ``"/v1/"`` → ``"/v1"``
        ``""`` → ``""``  (empty disables prefixing)
    """
    trimmed = api_version.strip("/")
    if trimmed == "":
        return ""
    return f"/{trimmed}"
