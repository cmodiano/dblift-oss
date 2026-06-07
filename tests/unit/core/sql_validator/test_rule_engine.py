"""Tests for the RuleEngine class."""

from pathlib import Path

import pytest

from core.sql_validator.linting.models import ViolationSeverity, ViolationSource
from core.sql_validator.linting.rule_engine import RuleEngine

pytestmark = [pytest.mark.unit]


class TestRuleEngine:
    """Test RuleEngine functionality."""

    def test_init(self):
        """Test RuleEngine initialization."""
        engine = RuleEngine()
        assert engine.rules == []
        assert engine.naming_rules == []
        assert engine.pattern_rules == []

    def test_load_rules_from_dict(self):
        """Test loading rules from dictionary."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "test_rule",
                    "type": "naming",
                    "target": "table",
                    "pattern": "^test_.*$",
                    "message": "Test message",
                    "severity": "warning",
                }
            ]
        }

        engine.load_rules_from_dict(rules_data)

        assert len(engine.rules) == 1
        assert len(engine.naming_rules) == 1
        assert engine.naming_rules[0]["name"] == "test_rule"

    def test_categorize_rules(self):
        """Test rule categorization by type."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {"name": "naming_rule", "type": "naming"},
                {"name": "pattern_rule", "type": "pattern"},
                {"name": "presence_rule", "type": "presence"},
                {"name": "relational_rule", "type": "relational"},
            ]
        }

        engine.load_rules_from_dict(rules_data)

        assert len(engine.naming_rules) == 1
        assert len(engine.pattern_rules) == 1
        assert len(engine.presence_rules) == 1
        assert len(engine.relational_rules) == 1

    def test_naming_rule_table_valid(self):
        """Test naming rule for valid table name."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "table_naming",
                    "type": "naming",
                    "target": "table",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Table names must be lowercase snake_case",
                    "severity": "warning",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "CREATE TABLE users (id INT PRIMARY KEY);"
        violations = engine.check_sql(sql)

        assert len(violations) == 0

    def test_naming_rule_table_invalid(self):
        """Test naming rule for invalid table name."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "table_naming",
                    "type": "naming",
                    "target": "table",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Table names must be lowercase snake_case",
                    "severity": "warning",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "CREATE TABLE Users (id INT PRIMARY KEY);"  # Uppercase U
        violations = engine.check_sql(sql)

        assert len(violations) == 1
        assert violations[0].rule_id == "table_naming"
        assert violations[0].severity == ViolationSeverity.WARNING
        assert "Users" in violations[0].message

    def test_naming_rule_column_valid(self):
        """Test naming rule for valid column names."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "column_naming",
                    "type": "naming",
                    "target": "column",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Column names must be lowercase snake_case",
                    "severity": "warning",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "CREATE TABLE users (user_id INT, user_name VARCHAR(100));"
        violations = engine.check_sql(sql)

        assert len(violations) == 0

    def test_naming_rule_column_invalid(self):
        """Test naming rule for invalid column names."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "column_naming",
                    "type": "naming",
                    "target": "column",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Column names must be lowercase snake_case",
                    "severity": "warning",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "CREATE TABLE users (UserID INT, UserName VARCHAR(100));"
        violations = engine.check_sql(sql)

        assert len(violations) >= 1  # At least one violation
        assert all(v.rule_id == "column_naming" for v in violations)

    def test_pattern_rule_prohibit(self):
        """Test pattern rule with prohibited pattern."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "no_select_star",
                    "type": "pattern",
                    "prohibit": "SELECT *",
                    "message": "Avoid SELECT *, specify columns explicitly",
                    "severity": "info",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "SELECT * FROM users;"
        violations = engine.check_sql(sql)

        assert len(violations) == 1
        assert violations[0].rule_id == "no_select_star"
        assert violations[0].severity == ViolationSeverity.INFO

    def test_pattern_rule_regex(self):
        """Test pattern rule with regex."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "no_truncate",
                    "type": "pattern",
                    "regex": "TRUNCATE\\s+TABLE",
                    "message": "TRUNCATE TABLE is not allowed",
                    "severity": "error",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "TRUNCATE TABLE users;"
        violations = engine.check_sql(sql)

        assert len(violations) == 1
        assert violations[0].rule_id == "no_truncate"
        assert violations[0].severity == ViolationSeverity.ERROR

    def test_multiple_rules(self):
        """Test multiple rules applied to same SQL."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "table_naming",
                    "type": "naming",
                    "target": "table",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Table names must be lowercase snake_case",
                    "severity": "warning",
                },
                {
                    "name": "no_select_star",
                    "type": "pattern",
                    "prohibit": "SELECT *",
                    "message": "Avoid SELECT *",
                    "severity": "info",
                },
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = """
        CREATE TABLE Users (id INT);
        SELECT * FROM Users;
        """
        violations = engine.check_sql(sql)

        assert len(violations) == 2
        rule_ids = {v.rule_id for v in violations}
        assert "table_naming" in rule_ids
        assert "no_select_star" in rule_ids

    def test_case_insensitive_pattern_matching(self):
        """Test that pattern matching is case-insensitive."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "no_truncate",
                    "type": "pattern",
                    "regex": "TRUNCATE\\s+TABLE",
                    "message": "TRUNCATE TABLE is not allowed",
                    "severity": "error",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        # Test different cases
        for sql in ["TRUNCATE TABLE users;", "truncate table users;", "Truncate Table users;"]:
            violations = engine.check_sql(sql)
            assert len(violations) == 1, f"Failed for: {sql}"

    def test_no_violations_clean_sql(self):
        """Test that clean SQL produces no violations."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "table_naming",
                    "type": "naming",
                    "target": "table",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Table names must be lowercase snake_case",
                    "severity": "warning",
                },
                {
                    "name": "column_naming",
                    "type": "naming",
                    "target": "column",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "message": "Column names must be lowercase snake_case",
                    "severity": "warning",
                },
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = """
        CREATE TABLE users (
            user_id INT PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(255)
        );
        """
        violations = engine.check_sql(sql)

        assert len(violations) == 0

    def test_violation_source(self):
        """Test that violations have correct source."""
        engine = RuleEngine()
        rules_data = {
            "rules": [
                {
                    "name": "test_rule",
                    "type": "naming",
                    "target": "table",
                    "pattern": "^test_.*$",
                    "message": "Test",
                    "severity": "warning",
                }
            ]
        }
        engine.load_rules_from_dict(rules_data)

        sql = "CREATE TABLE users (id INT);"
        violations = engine.check_sql(sql)

        assert len(violations) == 1
        assert violations[0].source == ViolationSource.BUSINESS_RULE
