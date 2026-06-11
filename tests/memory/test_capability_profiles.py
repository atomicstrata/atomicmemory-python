"""Tests for the generic capability-profile API (parity with the TS SDK)."""

from __future__ import annotations

from atomicmemory.memory.capability_profiles import (
    CapabilityProfile,
    capability_gaps,
    satisfies_profile,
)
from atomicmemory.memory.types import (
    Capabilities,
    CapabilitiesExtensions,
    CapabilitiesRequiredScope,
)

# Sample profile: an audited ingest->search->replay path needs deterministic
# verbatim storage plus liveness (health) and version pinning (versioning).
_PROFILE = CapabilityProfile(ingest_modes=["text", "verbatim"], extensions=["health", "versioning"])


def _eligible_caps() -> Capabilities:
    return Capabilities(
        ingest_modes=["text", "messages", "verbatim"],
        required_scope=CapabilitiesRequiredScope(default=["user"]),
        extensions=CapabilitiesExtensions(versioning=True, health=True),
    )


def test_satisfies_profile_accepts_eligible_capabilities() -> None:
    caps = _eligible_caps()
    assert satisfies_profile(caps, _PROFILE) is True
    assert capability_gaps(caps, _PROFILE) == []


def test_rejects_missing_extension_and_names_the_gap() -> None:
    caps = _eligible_caps()
    caps.extensions.versioning = False
    assert satisfies_profile(caps, _PROFILE) is False
    gaps = capability_gaps(caps, _PROFILE)
    assert len(gaps) == 1
    assert gaps[0].kind == "extension"
    assert gaps[0].requirement == "versioning"


def test_rejects_missing_ingest_mode_and_names_the_gap() -> None:
    caps = _eligible_caps()
    caps.ingest_modes = ["text", "messages"]
    gaps = capability_gaps(caps, _PROFILE)
    assert len(gaps) == 1
    assert gaps[0].kind == "ingest_mode"
    assert gaps[0].requirement == "verbatim"


def test_reports_every_gap_when_multiple_unmet() -> None:
    caps = _eligible_caps()
    caps.ingest_modes = ["messages"]
    caps.extensions.health = False
    caps.extensions.versioning = False
    requirements = sorted(gap.requirement for gap in capability_gaps(caps, _PROFILE))
    assert requirements == ["health", "text", "verbatim", "versioning"]
