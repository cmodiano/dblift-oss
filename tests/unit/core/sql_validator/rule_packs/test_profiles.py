"""Tests for built-in DBLift SQL validation profiles."""

import pytest

from core.sql_validator.rule_packs.profiles import (
    RULE_PROFILES,
    get_rule_profile,
    list_rule_profiles,
)
from core.sql_validator.rule_packs.rule_selector import create_rules_from_selection

pytestmark = [pytest.mark.unit]


def test_profiles_are_listed_in_sorted_order():
    assert list_rule_profiles() == sorted(RULE_PROFILES)


def test_profile_lookup_is_case_insensitive_and_copies_selection():
    selection = get_rule_profile("Enterprise")

    assert selection
    assert selection == get_rule_profile("enterprise")
    selection.append("naming")
    assert get_rule_profile("enterprise") != selection


def test_unknown_profile_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown rule profile 'unknown'"):
        get_rule_profile("unknown")


def test_strict_and_technical_debt_profiles_are_distinct():
    assert get_rule_profile("strict") != get_rule_profile("technical-debt")
    assert "security" in get_rule_profile("strict")
    assert "security" not in get_rule_profile("technical-debt")


@pytest.mark.parametrize("profile", ["core", "enterprise", "strict", "technical-debt"])
def test_every_profile_resolves_to_rules(profile):
    rules_data = create_rules_from_selection(get_rule_profile(profile))

    assert "rules" in rules_data
    assert rules_data["rules"], f"{profile} should resolve to at least one rule"
