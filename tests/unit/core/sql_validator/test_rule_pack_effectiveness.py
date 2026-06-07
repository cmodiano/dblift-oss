"""Effectiveness tests for shipped SQL validation rule packs."""

from pathlib import Path

import pytest

from core.sql_validator.linting.rule_engine import RuleEngine

pytestmark = [pytest.mark.unit]


def _violations_for(pack_name: str, sql: str):
    engine = RuleEngine("postgresql")
    engine.load_rules_from_file(Path("core/sql_validator/rule_packs") / f"{pack_name}.yaml")
    return engine.check_sql(sql, Path("V1__test.sql"))


def test_security_pack_flags_grant_all_privileges():
    violations = _violations_for(
        "security",
        "GRANT ALL PRIVILEGES ON customer TO app_user;",
    )

    assert any(v.rule_id == "no_grant_all_privileges" for v in violations)


def test_security_pack_flags_dynamic_sql():
    violations = _violations_for(
        "security",
        "EXECUTE IMMEDIATE 'DROP TABLE customer';",
    )

    assert any(v.rule_id == "no_dynamic_sql_without_validation" for v in violations)


def test_best_practices_pack_flags_drop_without_backup():
    violations = _violations_for(
        "best_practices",
        "DROP TABLE customer;",
    )

    assert any(v.rule_id == "no_drop_without_backup" for v in violations)


def test_performance_pack_flags_select_star():
    violations = _violations_for(
        "performance",
        "SELECT * FROM customer;",
    )

    assert any(v.rule_id == "no_select_star" for v in violations)


def test_performance_pack_allows_select_star_in_views():
    violations = _violations_for(
        "performance",
        "CREATE VIEW customer_view AS SELECT * FROM customer;",
    )

    assert not any(v.rule_id in {"no_select_star", "no_select_star.exception"} for v in violations)


def test_enterprise_profile_rules_include_policy_metadata():
    violations = _violations_for(
        "security",
        "GRANT ALL PRIVILEGES ON customer TO app_user;",
    )

    violation = next(v for v in violations if v.rule_id == "no_grant_all_privileges")
    assert violation.rationale
    assert violation.remediation
    assert violation.control_mapping
    assert violation.override_policy


def test_enterprise_profile_select_star_rule_includes_policy_metadata():
    from core.sql_validator.rule_packs.profiles import get_rule_profile
    from core.sql_validator.rule_packs.rule_selector import RuleSelector

    selector = RuleSelector()
    rules = selector.select_rules(get_rule_profile("enterprise"))
    rule = next(rule for rule in rules["rules"] if rule["name"] == "no_select_star")

    assert rule["rationale"]
    assert rule["remediation"]
    assert rule["control_mapping"] == ["DBLIFT-PERF-001"]
    assert rule["override_policy"]["max_days"] == 90
