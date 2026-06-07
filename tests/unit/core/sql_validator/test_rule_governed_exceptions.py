"""Governed policy exceptions for SQL validation rules."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.sql_validator.linting.rule_engine import RuleEngine

pytestmark = [pytest.mark.unit]


def _engine_with_exception(exception):
    engine = RuleEngine("postgresql")
    engine.load_rules_from_dict(
        {
            "rules": [
                {
                    "name": "no_drop_table_without_ticket",
                    "type": "pattern",
                    "regex": "(?i)DROP\\s+TABLE",
                    "message": "DROP TABLE requires approved change evidence",
                    "severity": "error",
                    "exceptions": [exception],
                    "override_policy": {
                        "requires": ["owner", "reason", "ticket", "expires_at"],
                    },
                }
            ]
        }
    )
    return engine


def _engine_with_policy(exception, override_policy):
    engine = RuleEngine("postgresql")
    engine.load_rules_from_dict(
        {
            "rules": [
                {
                    "name": "no_drop_table_without_ticket",
                    "type": "pattern",
                    "regex": "(?i)DROP\\s+TABLE",
                    "message": "DROP TABLE requires approved change evidence",
                    "severity": "error",
                    "exceptions": [exception],
                    "override_policy": override_policy,
                }
            ]
        }
    )
    return engine


def test_governed_exception_suppresses_matching_violation():
    engine = _engine_with_exception(
        {
            "when": "DROP TABLE staging_import",
            "owner": "data-platform",
            "reason": "Ephemeral staging object",
            "ticket": "DBA-123",
            "expires_at": "2999-07-01",
        }
    )

    violations = engine.check_sql(
        "DROP TABLE staging_import;",
        Path("migrations/V9__drop_staging_import.sql"),
    )

    assert violations == []


def test_incomplete_governed_exception_emits_error_finding():
    engine = _engine_with_exception(
        {
            "when": "DROP TABLE staging_import",
            "owner": "data-platform",
            "reason": "Ephemeral staging object",
        }
    )

    violations = engine.check_sql(
        "DROP TABLE staging_import;",
        Path("migrations/V9__drop_staging_import.sql"),
    )

    assert len(violations) == 1
    assert violations[0].rule_id == "no_drop_table_without_ticket.exception"
    assert violations[0].severity.value == "error"
    assert "ticket" in violations[0].message
    assert "expires_at" in violations[0].message


def test_governed_exception_enforces_max_days():
    engine = _engine_with_policy(
        {
            "when": "DROP TABLE staging_import",
            "owner": "data-platform",
            "reason": "Ephemeral staging object",
            "ticket": "DBA-123",
            "expires_at": (date.today() + timedelta(days=31)).isoformat(),
        },
        {
            "requires": ["owner", "reason", "ticket", "expires_at"],
            "max_days": 30,
        },
    )

    violations = engine.check_sql(
        "DROP TABLE staging_import;",
        Path("migrations/V9__drop_staging_import.sql"),
    )

    assert len(violations) == 1
    assert violations[0].rule_id == "no_drop_table_without_ticket.exception"
    assert "expires_at:within_30_days" in violations[0].message


def test_max_days_requires_exception_expiration():
    engine = _engine_with_policy(
        {
            "when": "DROP TABLE staging_import",
            "owner": "data-platform",
            "reason": "Ephemeral staging object",
            "ticket": "DBA-123",
        },
        {
            "requires": ["owner", "reason", "ticket"],
            "max_days": 30,
        },
    )

    violations = engine.check_sql(
        "DROP TABLE staging_import;",
        Path("migrations/V9__drop_staging_import.sql"),
    )

    assert len(violations) == 1
    assert violations[0].rule_id == "no_drop_table_without_ticket.exception"
    assert "expires_at" in violations[0].message


def test_governed_exception_serializes_yaml_date_values():
    expires_at = date.today() + timedelta(days=31)
    engine = _engine_with_policy(
        {
            "when": "DROP TABLE staging_import",
            "owner": "data-platform",
            "reason": "Ephemeral staging object",
            "ticket": "DBA-123",
            "expires_at": expires_at,
        },
        {
            "requires": ["owner", "reason", "ticket", "expires_at"],
            "max_days": 30,
        },
    )

    violations = engine.check_sql(
        "DROP TABLE staging_import;",
        Path("migrations/V9__drop_staging_import.sql"),
    )

    assert len(violations) == 1
    assert violations[0].exception == {
        "when": "DROP TABLE staging_import",
        "owner": "data-platform",
        "reason": "Ephemeral staging object",
        "ticket": "DBA-123",
        "expires_at": expires_at.isoformat(),
    }
    json.dumps(violations[0].to_dict())
