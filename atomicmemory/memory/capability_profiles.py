"""Capability profiles.

A capability profile is the minimum :class:`Capabilities` a memory provider
must satisfy for a given consumer's needs (for example, an audited
ingest->search->replay path that requires deterministic verbatim storage and
version pinning). It is a typed, partial requirement set so a caller can gate a
provider at wiring time with an actionable diff instead of an opaque boolean.

Port of ``atomicmemory-sdk/src/memory/capability-profiles.ts``. The SDK ships
the generic mechanism; each consumer defines its own profile against it. Pure
runtime code -- no I/O, no provider construction.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from atomicmemory.memory.types import Capabilities, IngestMode


class CapabilityProfile(BaseModel):
    """Minimum capability requirement set a provider must satisfy.

    ``extensions`` lists the boolean flag names on
    :class:`CapabilitiesExtensions` that must be ``True`` (e.g. ``"health"``,
    ``"versioning"``). ``search`` is not listed -- it is a core method every
    provider implements, so it is implied rather than gated.
    """

    model_config = ConfigDict(extra="forbid")

    ingest_modes: list[IngestMode] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)


class CapabilityGap(BaseModel):
    """A single unmet capability requirement, for actionable rejection errors."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["ingest_mode", "extension"]
    requirement: str
    detail: str


def capability_gaps(caps: Capabilities, profile: CapabilityProfile) -> list[CapabilityGap]:
    """Return every requirement in ``profile`` that ``caps`` fails to satisfy.

    An empty list means the provider satisfies the profile. Use this to build
    actionable errors ("provider X is missing verbatim ingest, missing
    versioning extension") instead of an opaque boolean rejection.
    """
    gaps: list[CapabilityGap] = []
    for mode in profile.ingest_modes:
        if mode not in caps.ingest_modes:
            gaps.append(
                CapabilityGap(
                    kind="ingest_mode",
                    requirement=mode,
                    detail=f"ingest_modes must include '{mode}'",
                )
            )
    for extension in profile.extensions:
        if getattr(caps.extensions, extension, False) is not True:
            gaps.append(
                CapabilityGap(
                    kind="extension",
                    requirement=extension,
                    detail=f"extensions.{extension} must be true",
                )
            )
    return gaps


def satisfies_profile(caps: Capabilities, profile: CapabilityProfile) -> bool:
    """Whether ``caps`` satisfies every requirement in ``profile``."""
    return len(capability_gaps(caps, profile)) == 0
