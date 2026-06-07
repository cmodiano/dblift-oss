"""DBLift rule packs for SQL validation.

This module provides predefined rule packs for SQL validation.
These rule packs cover common database best practices, performance optimization,
security, and naming conventions.

Available rule packs:
- naming: Naming conventions for database objects
- best_practices: Common SQL best practices for database migrations
- security: Security-focused validation rules
- performance: Performance optimization rules
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.sql_validator.rule_packs.profiles import (
    RULE_PROFILES,
    get_rule_profile,
    list_rule_profiles,
)
from core.sql_validator.rule_packs.resolver import (
    parse_rule_selection,
    resolve_validation_rules,
)
from core.sql_validator.rule_packs.rule_selector import (
    RuleSelector,
    create_rules_from_selection,
)

logger = logging.getLogger(__name__)

# Base directory for rule packs
_RULE_PACKS_DIR = Path(__file__).parent

# Available rule packs
RULE_PACKS: Dict[str, Path] = {
    "naming": _RULE_PACKS_DIR / "naming.yaml",
    "best_practices": _RULE_PACKS_DIR / "best_practices.yaml",
    "security": _RULE_PACKS_DIR / "security.yaml",
    "performance": _RULE_PACKS_DIR / "performance.yaml",
}


def get_rule_pack_path(pack_name: str) -> Optional[Path]:
    """
    Get the path to a predefined rule pack.

    Args:
        pack_name: Name of the rule pack (flyway_compatible, best_practices, security, performance)

    Returns:
        Path to the rule pack YAML file, or None if not found

    Examples:
        >>> pack_path = get_rule_pack_path("flyway_compatible")
        >>> print(pack_path)
        /path/to/core/migration/validation/rule_packs/flyway_compatible.yaml
    """
    return RULE_PACKS.get(pack_name)


def list_available_rule_packs() -> list[str]:
    """
    List all available predefined rule packs.

    Returns:
        List of available rule pack names

    Examples:
        >>> packs = list_available_rule_packs()
        >>> print(packs)
        ['flyway_compatible', 'best_practices', 'security', 'performance']
    """
    return list(RULE_PACKS.keys())


def load_rule_pack(pack_name: str) -> Optional[Dict[str, Any]]:
    """
    Load a predefined rule pack as a dictionary.

    Args:
        pack_name: Name of the rule pack to load

    Returns:
        Dictionary containing the rule pack data, or None if not found

    Examples:
        >>> rules = load_rule_pack("flyway_compatible")
        >>> print(rules["rules"][0]["name"])
        no_ddl_in_transaction_without_commit
    """
    import yaml  # type: ignore[import-untyped]

    pack_path = get_rule_pack_path(pack_name)
    if not pack_path or not pack_path.exists():
        return None

    try:
        with open(pack_path, "r", encoding="utf-8") as f:
            pack_data = yaml.safe_load(f)
            if pack_data is None:
                logger.warning("Rule pack '%s' is empty.", pack_name)
                return None
            if not isinstance(pack_data, dict):
                logger.error(
                    "Rule pack '%s' has invalid format. Expected a dictionary at the top level.",
                    pack_name,
                )
                return None
            return pack_data
    except Exception as e:
        logger.error(f"Failed to load rule pack {pack_name}: {e}")
        return None


__all__ = [
    "RULE_PACKS",
    "get_rule_pack_path",
    "list_available_rule_packs",
    "load_rule_pack",
    "RULE_PROFILES",
    "get_rule_profile",
    "list_rule_profiles",
    "parse_rule_selection",
    "resolve_validation_rules",
    "RuleSelector",
    "create_rules_from_selection",
]
