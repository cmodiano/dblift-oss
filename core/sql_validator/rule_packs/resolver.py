"""Resolve configured SQL validation profiles and rule selections."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, List, Optional

from config.validation_config import ValidationConfig
from core.sql_validator.rule_packs.profiles import get_rule_profile
from core.sql_validator.rule_packs.rule_selector import create_rules_from_selection


def _iter_rule_selection_values(values: Iterable[Any]) -> Iterator[str]:
    """Yield raw rule selection values from argparse/config shapes."""
    for value in values:
        if isinstance(value, (list, tuple)):
            yield from _iter_rule_selection_values(value)
        else:
            yield str(value)


def parse_rule_selection(values: Optional[Iterable[Any]]) -> List[str]:
    """Normalize comma-separated and repeated rule selection values."""
    selections: List[str] = []
    for value in _iter_rule_selection_values(values or []):
        for item in str(value).split(","):
            normalized = item.strip()
            if normalized:
                selections.append(normalized)
    return selections


def resolve_validation_rules(config: ValidationConfig) -> Optional[dict[str, Any]]:
    """Resolve configured profile/rule selections into RuleEngine-compatible data."""
    if config.rules_file and (config.rule_profile or config.rules):
        raise ValueError("--rules-file cannot be combined with --profile or --rules")

    selections: List[str | dict[str, Any]] = []
    if config.rule_profile:
        selections.extend(get_rule_profile(config.rule_profile))
    selections.extend(config.rules)
    if not selections:
        return None
    return create_rules_from_selection(selections)
