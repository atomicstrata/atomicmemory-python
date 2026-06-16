"""Mem0 provider configuration.

Port of `atomicmemory-sdk/src/memory/mem0-provider/types.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atomicmemory.core.url import validate_api_url

MEM0_DEFAULT_TIMEOUT_SECONDS: float = 30.0
MEM0_DEFAULT_PATH_PREFIX: str = "/v1"


class Mem0ProviderConfig(BaseModel):
    """Inputs to construct a Mem0 provider."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_url: str = Field(alias="apiUrl")
    """Mem0 API base URL.

    Hosted: ``https://api.mem0.ai``. OSS self-hosted:
    ``http://localhost:8888``.
    """

    api_key: str | None = Field(default=None, alias="apiKey")
    """API key for hosted Mem0 instances. Sent as ``Authorization: Bearer …``."""

    timeout_seconds: float = Field(
        default=MEM0_DEFAULT_TIMEOUT_SECONDS,
        alias="timeoutSeconds",
    )

    default_infer: bool = Field(default=True, alias="defaultInfer")
    """Whether to enable LLM inference on ingest by default."""

    defer_inference: bool = Field(default=False, alias="deferInference")
    """When True, ingest sends ``infer=false`` synchronously and fires a
    background re-ingest with ``infer=true`` (deferred AUDN extraction).
    Only applies when the effective infer value would be True. Default
    False (single-call behaviour)."""

    path_prefix: str = Field(default=MEM0_DEFAULT_PATH_PREFIX, alias="pathPrefix")
    """Path prefix for memory-identifier endpoints.

    ``/v1`` (default) for hosted Mem0; ``''`` for OSS self-hosted. Note
    that search uses the v2 endpoint regardless of this prefix.
    """

    org_id: str | None = Field(default=None, alias="orgId")
    project_id: str | None = Field(default=None, alias="projectId")

    allow_private_networks: bool = Field(default=True, alias="allowPrivateNetworks")
    """Permit loopback/private/reserved IP literals in ``api_url`` (default True;
    set False to harden). Link-local / cloud-metadata stay blocked regardless."""

    @model_validator(mode="after")
    def _validate_api_url(self) -> Mem0ProviderConfig:
        self.api_url = validate_api_url(self.api_url, allow_private_networks=self.allow_private_networks)
        return self
