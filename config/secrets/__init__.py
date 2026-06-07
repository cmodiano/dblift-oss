"""Secrets resolution stub for OSS edition.

Secret URI providers (vault://, aws-secrets://, azure-keyvault://, etc.) are
an enterprise feature. This stub keeps the config layer importable without
any external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SecretsConfig:
    """No-op secrets config for OSS edition."""

    vault: Optional[Any] = None
    aws: Optional[Any] = None
    azure: Optional[Any] = None
    gcp: Optional[Any] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SecretsConfig":
        return cls()


def resolve_secret_refs(data: Any, secrets_config: Optional[SecretsConfig] = None) -> Any:
    """In OSS, secret URI resolution is a no-op — return data unchanged."""
    return data


__all__ = ["SecretsConfig", "resolve_secret_refs"]
