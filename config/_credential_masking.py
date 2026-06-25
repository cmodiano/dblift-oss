"""Credential-masking helpers for :class:`BaseDatabaseConfig.to_safe_dict`.

Extracted from ``config.database_config`` during PR-H10 so the facade
module stays under its 500-line budget. Pure functions with no side
effects; behaviour matches the original inline implementation byte-for-byte.
"""

import re
from typing import Any, Dict

# Sensitive key patterns (case-insensitive matching)
_SENSITIVE_PATTERNS = (
    "password",
    "pwd",
    "secret",
    "key",
    "token",
    "credential",
    "api_key",
    "apikey",
    "auth",
    "access_token",
    "private",
)


def is_sensitive_key(key: str) -> bool:
    """Return True if ``key`` looks like it names sensitive data."""
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in _SENSITIVE_PATTERNS)


def mask_url_credentials(url: str) -> str:
    """Mask ``password=...`` parameters and ``user:pass@`` segments in ``url``."""
    # Pattern for password=xxx or password=xxx; or password=xxx&
    url = re.sub(r"(password=)[^;&\s]+", r"\1***MASKED***", url, flags=re.IGNORECASE)
    # Pattern for user:password@ in URLs
    url = re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***MASKED***\2", url)
    return url


def mask_dict_in_place(result: Dict[str, Any], field_name: str) -> None:
    """Mask sensitive keys in ``result[field_name]`` (a dict) if present."""
    if not result.get(field_name):
        return
    masked = dict(result[field_name])
    for key in list(masked.keys()):
        if is_sensitive_key(key):
            masked[key] = "***MASKED***"
    result[field_name] = masked


def mask_credentials(result: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all credential-masking rules to ``result`` and return it.

    Mutates ``result`` in place but also returns it for fluent use.
    """
    # Mask password
    if result.get("password"):
        result["password"] = "***MASKED***"

    # Mask URL if it contains credentials
    url = result.get("url", "")
    if url:
        result["url"] = mask_url_credentials(url)

    # Mask any sensitive keys in extra_params / properties (case-insensitive)
    mask_dict_in_place(result, "extra_params")
    mask_dict_in_place(result, "properties")

    return result
