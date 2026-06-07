"""Tests for resolving SQL validation rule selections."""

import pytest

from config.validation_config import ValidationConfig
from core.sql_validator.rule_packs.resolver import (
    parse_rule_selection,
    resolve_validation_rules,
)

pytestmark = [pytest.mark.unit]


def test_parse_rule_selection_accepts_comma_and_space_separated_values():
    assert parse_rule_selection(["security,best_practices", "no_grant_all_privileges"]) == [
        "security",
        "best_practices",
        "no_grant_all_privileges",
    ]


def test_parse_rule_selection_accepts_repeated_argparse_values():
    assert parse_rule_selection([["security,best_practices"], ["performance"]]) == [
        "security",
        "best_practices",
        "performance",
    ]


def test_parse_rule_selection_ignores_empty_values():
    assert parse_rule_selection(["security,,", "  ", "performance"]) == [
        "security",
        "performance",
    ]


def test_resolve_validation_rules_returns_none_without_selection():
    assert resolve_validation_rules(ValidationConfig()) is None


def test_resolve_validation_rules_uses_profile_and_extra_rules():
    config = ValidationConfig(
        rule_profile="core",
        rules=["no_grant_all_privileges"],
    )

    rules_data = resolve_validation_rules(config)

    assert rules_data is not None
    rule_names = {rule["name"] for rule in rules_data["rules"]}
    assert "no_grant_all_privileges" in rule_names
    assert "require_primary_key" in rule_names


def test_resolve_validation_rules_rejects_unknown_profile():
    with pytest.raises(ValueError, match="Unknown rule profile 'missing'"):
        resolve_validation_rules(ValidationConfig(rule_profile="missing"))


def test_resolve_validation_rules_rejects_mutated_conflicting_rule_sources():
    config = ValidationConfig(rules_file=".my_rules.yaml")
    config.rule_profile = "core"

    with pytest.raises(ValueError, match="--rules-file cannot be combined"):
        resolve_validation_rules(config)
