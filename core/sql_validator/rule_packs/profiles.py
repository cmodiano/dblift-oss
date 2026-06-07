"""Built-in rule profiles for SQL validation."""

from __future__ import annotations

from typing import Dict, List

RULE_PROFILES: Dict[str, List[str]] = {
    "core": [
        "security",
        "no_drop_without_backup",
        "update_delete_must_have_where",
        "require_primary_key",
    ],
    "enterprise": [
        "security",
        "best_practices",
        "performance",
    ],
    "strict": [
        "naming",
        "security",
        "best_practices",
        "performance",
    ],
    "technical-debt": [
        "naming",
        "best_practices",
        "performance",
    ],
}


def list_rule_profiles() -> list[str]:
    """Return supported profile names in stable order."""
    return sorted(RULE_PROFILES)


def get_rule_profile(profile_name: str) -> list[str]:
    """Return a copy of the rule selection for a built-in profile."""
    normalized = (profile_name or "").strip().lower()
    if normalized not in RULE_PROFILES:
        available = ", ".join(list_rule_profiles())
        raise ValueError(f"Unknown rule profile '{profile_name}'. Available profiles: {available}")
    return list(RULE_PROFILES[normalized])
