"""SSRF-guard coverage for every SDK config that accepts ``api_url``.

Each provider/client config must always reject the AWS IMDS link-local
endpoint (and its encodings), while allowing private/loopback IP literals
by default (posture B — local/self-hosted cores) and rejecting them only
when ``allow_private_networks=False``. This pins the consistency the
FailSafe report (AGNT-PY-001) found missing: previously only the
storage/client configs validated the URL while the provider configs
accepted any string.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from pydantic import BaseModel, ValidationError

import atomicmemory
from atomicmemory.client.atomic_memory_client import AtomicMemoryClientConfig
from atomicmemory.providers.atomicmemory.config import AtomicMemoryProviderConfig
from atomicmemory.providers.hindsight.config import HindsightProviderConfig
from atomicmemory.providers.mem0.config import Mem0ProviderConfig
from atomicmemory.storage.types import StorageClientConfig

_IMDS = "http://169.254.169.254/latest/meta-data/"
_LOOPBACK = "http://127.0.0.1:17350"


def _client_kwargs(api_url: str, **extra: object) -> dict[str, object]:
    return {"apiUrl": api_url, "apiKey": "secret", "userId": "u1", **extra}


def test_provider_configs_reject_imds_endpoint() -> None:
    for factory in (
        lambda u: AtomicMemoryProviderConfig(apiUrl=u),
        lambda u: HindsightProviderConfig(apiUrl=u),
        lambda u: Mem0ProviderConfig(apiUrl=u),
    ):
        with pytest.raises(ValidationError):
            factory(_IMDS)


def test_client_configs_reject_imds_endpoint() -> None:
    with pytest.raises(ValidationError):
        StorageClientConfig(**_client_kwargs(_IMDS))
    with pytest.raises(ValidationError):
        AtomicMemoryClientConfig(**_client_kwargs(_IMDS))


def test_provider_config_allows_loopback_ip_by_default() -> None:
    # Posture B: providers connect to local/self-hosted cores by default.
    cfg = AtomicMemoryProviderConfig(apiUrl=_LOOPBACK)
    assert cfg.api_url == _LOOPBACK


def test_provider_config_rejects_loopback_ip_when_strict() -> None:
    with pytest.raises(ValidationError):
        AtomicMemoryProviderConfig(apiUrl=_LOOPBACK, allowPrivateNetworks=False)


def test_imds_rejected_even_with_private_networks_allowed() -> None:
    with pytest.raises(ValidationError):
        AtomicMemoryProviderConfig(apiUrl=_IMDS, allowPrivateNetworks=True)


def test_localhost_hostname_still_allowed_when_strict() -> None:
    # Hostnames are not DNS-resolved, so localhost passes even in strict mode.
    cfg = Mem0ProviderConfig(apiUrl="http://localhost:8888", allowPrivateNetworks=False)
    assert cfg.api_url == "http://localhost:8888"


def test_config_rejects_decimal_encoded_imds() -> None:
    # The numeric-encoding bypass must be closed end-to-end through a config,
    # not just in the standalone validator: http://2852039166/ == IMDS.
    with pytest.raises(ValidationError):
        AtomicMemoryProviderConfig(apiUrl="http://2852039166/latest/meta-data/", allowPrivateNetworks=True)


def test_entities_config_rejects_imds_literal_and_encoded() -> None:
    # EntitiesClientConfig (shared by sync + async entities clients) is the 6th
    # api_url config and must enforce the same SSRF guard.
    from atomicmemory.entities.client import EntitiesClientConfig

    for url in (_IMDS, "http://2852039166/latest/meta-data/"):
        with pytest.raises(ValidationError):
            EntitiesClientConfig(apiUrl=url, apiKey="secret")


def test_entities_config_allows_loopback_by_default_blocks_when_strict() -> None:
    from atomicmemory.entities.client import EntitiesClientConfig

    ok = EntitiesClientConfig(apiUrl=_LOOPBACK, apiKey="secret")
    assert ok.api_url == _LOOPBACK
    with pytest.raises(ValidationError):
        EntitiesClientConfig(apiUrl=_LOOPBACK, apiKey="secret", allowPrivateNetworks=False)
    host = EntitiesClientConfig(apiUrl="http://localhost:8888", apiKey="secret")
    assert host.api_url == "http://localhost:8888"


def _discover_api_url_configs() -> list[type[BaseModel]]:
    """Every Pydantic config in the package that exposes an ``api_url`` field.

    Imports the whole ``atomicmemory`` package so a newly added config is
    discovered automatically — this is the guard that fails when a future
    config forgets the shared SSRF validator (the exact gap AGNT-PY-001 and
    its EntitiesClientConfig follow-up were).
    """
    for mod in pkgutil.walk_packages(atomicmemory.__path__, "atomicmemory."):
        importlib.import_module(mod.name)
    found: dict[type[BaseModel], None] = {}

    def walk(cls: type[BaseModel]) -> None:
        for sub in cls.__subclasses__():
            if "api_url" in sub.model_fields:
                found[sub] = None
            walk(sub)

    walk(BaseModel)
    return list(found)


def _dummy_required_kwargs(model: type[BaseModel]) -> dict[str, object]:
    """Minimal valid kwargs (by alias) for every required field except api_url."""
    kwargs: dict[str, object] = {}
    for name, field in model.model_fields.items():
        if name == "api_url" or not field.is_required():
            continue
        kwargs[field.alias or name] = "x"
    return kwargs


def test_every_api_url_config_blocks_imds() -> None:
    configs = _discover_api_url_configs()
    assert len(configs) >= 6, f"expected to discover >= 6 api_url configs, found {len(configs)}: {configs}"
    for model in configs:
        with pytest.raises(ValidationError):
            model(apiUrl=_IMDS, **_dummy_required_kwargs(model))
