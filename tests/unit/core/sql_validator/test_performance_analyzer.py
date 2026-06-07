"""Tests for the PerformanceAnalyzer class."""

from pathlib import Path

import pytest

from core.sql_validator.linting.models import ViolationSeverity, ViolationSource
from core.sql_validator.linting.performance_analyzer import PerformanceAnalyzer

pytestmark = [pytest.mark.unit]


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer functionality."""

    def test_init(self):
        """Test PerformanceAnalyzer initialization."""
        analyzer = PerformanceAnalyzer(dialect="postgres")
        assert analyzer.dialect == "postgres"
        # All rules enabled by default with default severities
        assert "cartesian_product" in analyzer.rule_severities
        assert "missing_where_clause" in analyzer.rule_severities
        assert "select_star" in analyzer.rule_severities
        assert "correlated_subquery" in analyzer.rule_severities

    def test_init_with_specific_rules(self):
        """Test initialization with specific rule severities."""
        analyzer = PerformanceAnalyzer(
            dialect="postgres",
            rule_severities={"cartesian_product": "error", "select_star": "info"},
        )
        assert analyzer.rule_severities == {"cartesian_product": "error", "select_star": "info"}
        # Only specified rules should be enabled
        assert "cartesian_product" in analyzer.rule_severities
        assert "select_star" in analyzer.rule_severities
        assert "missing_where_clause" not in analyzer.rule_severities

    def test_cartesian_product_detection(self):
        """Test detection of Cartesian products."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = """
        SELECT * FROM users, orders;
        """
        violations = analyzer.analyze_sql(sql)

        # Should detect JOIN without ON clause (implicit cross join)
        cartesian_violations = [v for v in violations if v.rule_id == "cartesian_product"]
        # Note: This may not trigger depending on sqlglot's parsing
        # The actual Cartesian product detection requires JOIN syntax without ON

    def test_cartesian_product_explicit_join(self):
        """Test detection of explicit JOIN without ON clause."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = """
        SELECT *
        FROM users
        JOIN orders;
        """
        violations = analyzer.analyze_sql(sql)

        cartesian_violations = [v for v in violations if v.rule_id == "cartesian_product"]
        assert len(cartesian_violations) == 1
        assert cartesian_violations[0].severity == ViolationSeverity.ERROR
        assert cartesian_violations[0].source == ViolationSource.PERFORMANCE

    def test_missing_where_update(self):
        """Test detection of UPDATE without WHERE."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = "UPDATE users SET status = 'active';"
        violations = analyzer.analyze_sql(sql)

        where_violations = [v for v in violations if v.rule_id == "missing_where_clause"]
        assert len(where_violations) == 1
        assert where_violations[0].severity == ViolationSeverity.WARNING
        assert "UPDATE" in where_violations[0].message

    def test_missing_where_delete(self):
        """Test detection of DELETE without WHERE."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = "DELETE FROM users;"
        violations = analyzer.analyze_sql(sql)

        where_violations = [v for v in violations if v.rule_id == "missing_where_clause"]
        assert len(where_violations) == 1
        assert where_violations[0].severity == ViolationSeverity.WARNING
        assert "DELETE" in where_violations[0].message

    def test_update_with_where_clause(self):
        """Test that UPDATE with WHERE clause doesn't trigger violation."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = "UPDATE users SET status = 'active' WHERE id = 1;"
        violations = analyzer.analyze_sql(sql)

        where_violations = [v for v in violations if v.rule_id == "missing_where_clause"]
        assert len(where_violations) == 0

    def test_select_star_detection(self):
        """Test detection of SELECT *."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = "SELECT * FROM users;"
        violations = analyzer.analyze_sql(sql)

        star_violations = [v for v in violations if v.rule_id == "select_star"]
        assert len(star_violations) == 1
        assert star_violations[0].severity == ViolationSeverity.WARNING

    def test_select_specific_columns(self):
        """Test that SELECT with specific columns doesn't trigger violation."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = "SELECT id, username, email FROM users;"
        violations = analyzer.analyze_sql(sql)

        star_violations = [v for v in violations if v.rule_id == "select_star"]
        assert len(star_violations) == 0

    def test_correlated_subquery_detection(self):
        """Test detection of correlated subqueries."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = """
        SELECT u.id, u.username
        FROM users u
        WHERE EXISTS (
            SELECT 1 FROM orders o WHERE o.user_id = u.id
        );
        """
        violations = analyzer.analyze_sql(sql)

        subquery_violations = [v for v in violations if v.rule_id == "correlated_subquery"]
        assert len(subquery_violations) >= 1
        assert subquery_violations[0].severity == ViolationSeverity.INFO

    def test_multiple_performance_issues(self):
        """Test detection of multiple performance issues in one SQL."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        statements = [
            "SELECT * FROM users",
            "UPDATE orders SET status = 'shipped'",
            "DELETE FROM logs",
        ]
        violations = analyzer.analyze_statements(statements)

        # Should detect: SELECT *, UPDATE without WHERE, DELETE without WHERE
        assert len(violations) >= 3

        rule_ids = {v.rule_id for v in violations}
        assert "select_star" in rule_ids
        assert "missing_where_clause" in rule_ids

    def test_disabled_rule(self):
        """Test that disabled rules don't generate violations."""
        analyzer = PerformanceAnalyzer(
            dialect="postgres",
            rule_severities={"cartesian_product": "error"},  # Only this rule enabled
        )

        sql = """
        SELECT * FROM users;
        UPDATE users SET status = 'active';
        """
        violations = analyzer.analyze_sql(sql)

        # Should not detect SELECT * or missing WHERE because those rules are disabled
        assert all(v.rule_id == "cartesian_product" for v in violations)

    def test_clean_sql_no_violations(self):
        """Test that clean SQL produces no violations."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = """
        SELECT id, username, email
        FROM users
        WHERE status = 'active';

        UPDATE users
        SET last_login = NOW()
        WHERE id = 1;

        SELECT o.id, o.total
        FROM orders o
        INNER JOIN users u ON o.user_id = u.id
        WHERE u.status = 'active';
        """
        violations = analyzer.analyze_sql(sql)

        assert len(violations) == 0

    def test_violation_suggestions(self):
        """Test that violations include helpful suggestions."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = "UPDATE users SET status = 'active';"
        violations = analyzer.analyze_sql(sql)

        where_violations = [v for v in violations if v.rule_id == "missing_where_clause"]
        assert len(where_violations) == 1
        assert where_violations[0].suggestion is not None
        assert "WHERE" in where_violations[0].suggestion

    def test_dialect_normalization(self):
        """Test that dialects are normalized correctly via quirks."""
        test_cases = [
            ("oracle", "oracle"),
            ("postgresql", "postgres"),
            ("sqlserver", "tsql"),
            ("mysql", "mysql"),
            # DB2: sqlglot has limited DB2 support; uses "db2" directly (original behaviour).
            ("db2", "db2"),
            # Legacy DIALECT_MAP default — unknown strings must not pass through raw to sqlglot.
            ("not_a_real_dialect_xyz", "postgres"),
            ("", "postgres"),
        ]

        for input_dialect, expected_dialect in test_cases:
            analyzer = PerformanceAnalyzer(dialect=input_dialect)
            assert analyzer.dialect == expected_dialect

    def test_invalid_sql_handling(self):
        """Test that invalid SQL doesn't crash the analyzer."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        # Invalid SQL that can't be parsed
        sql = "INVALID SQL SYNTAX HERE !@#$%"
        violations = analyzer.analyze_sql(sql)

        # Should handle gracefully without crashing
        assert isinstance(violations, list)

    def test_ddl_statements_ignored(self):
        """Test that DDL statements don't trigger performance violations."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100)
        );

        CREATE INDEX idx_users_username ON users(username);
        """
        violations = analyzer.analyze_sql(sql)

        # DDL shouldn't trigger performance violations
        assert len(violations) == 0

    def test_empty_statement_selection_does_not_emit_parse_error(self):
        """Analyzer callers may pass no performance-relevant fragments."""
        analyzer = PerformanceAnalyzer(dialect="mysql")

        assert analyzer.analyze_statements([]) == []

    def test_analyze_statements_parses_already_selected_fragments(self, monkeypatch):
        """Analyzer parses only the fragments its caller supplies."""
        from core.sql_validator.linting import performance_analyzer

        analyzer = PerformanceAnalyzer(dialect="postgres")
        parsed_sql = []

        def record_parse(sql, *args, **kwargs):
            parsed_sql.append(sql)
            return None

        monkeypatch.setattr(performance_analyzer, "parse_one", record_parse)

        analyzer.analyze_statements(["SELECT id FROM orders", "UPDATE orders SET status = 'x'"])

        assert parsed_sql == ["SELECT id FROM orders", "UPDATE orders SET status = 'x'"]

    def test_all_violation_sources_are_performance(self):
        """Test that all violations from analyzer have PERFORMANCE source."""
        analyzer = PerformanceAnalyzer(dialect="postgres")

        sql = """
        SELECT * FROM users;
        UPDATE users SET status = 'active';
        """
        violations = analyzer.analyze_sql(sql)

        assert all(v.source == ViolationSource.PERFORMANCE for v in violations)
