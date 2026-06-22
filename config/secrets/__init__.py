"""OSS secrets: environment-variable resolution and the custom-provider
registration seam. No built-in external vault providers ship in OSS."""

from config.secrets._provider_base import AbstractSecretsProvider, SecretsResolutionError
from config.secrets._registry import register_provider
from config.secrets._resolver import clear_cache, resolve_secret_refs
from config.secrets._secrets_config import SecretsConfig

__all__ = [
    "resolve_secret_refs",
    "clear_cache",
    "SecretsResolutionError",
    "SecretsConfig",
    "AbstractSecretsProvider",
    "register_provider",
]
