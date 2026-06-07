"""BUG-06 regression: parse/tokenizer errors in validate-sql fail exit code.

Before the fix, sqlglot ``Error tokenizing '...'`` on dollar-quoted
PL/pgSQL bodies was caught in ``PerformanceAnalyzer._parse_sql``, logged
at debug, and silently dropped. ``analyze_sql`` returned an empty list,
``ValidationResult`` showed zero violations, and ``validate-sql`` exited
0 with "No issues found" — over content the parser could not parse.

The fix surfaces parse errors as ERROR-severity ``parse_error`` violations
and makes the default ``--fail-on error`` threshold fail on them.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlglot.errors import ParseError

from core.sql_validator.linting.models import (
    ValidationResult,
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)
from core.sql_validator.linting.performance_analyzer import PerformanceAnalyzer
from core.sql_validator.linting.sql_validator import SqlValidator


@pytest.mark.unit
class TestParseErrorBecomesViolation:
    def test_tokenizer_error_emits_parse_error_violation(self):
        analyzer = PerformanceAnalyzer(dialect="postgres")
        sql_with_dollar_body = "CREATE FUNCTION get_x() RETURNS NUMERIC AS $$ DECLARE x INT; BEGIN RETURN 1; END $$ LANGUAGE plpgsql;"

        # Real sqlglot may or may not reject this; inject a failure deterministically.
        with patch.object(
            analyzer,
            "_parse_statement",
            side_effect=ParseError("Error tokenizing 'RETURNS NUMERIC AS $$'"),
        ):
            violations = analyzer.analyze_sql(sql_with_dollar_body, Path("V1.sql"))

        assert len(violations) == 1
        v = violations[0]
        assert v.rule_id == "parse_error"
        assert v.severity == ViolationSeverity.ERROR
        assert v.source == ViolationSource.SYNTAX
        assert "Error tokenizing" in v.message

    def test_no_parse_error_means_no_syntax_violation(self):
        """Happy path: clean SQL produces no parse_error violations."""
        analyzer = PerformanceAnalyzer(dialect="postgres")
        violations = analyzer.analyze_sql("SELECT 1;", Path("V1.sql"))

        assert not any(v.rule_id == "parse_error" for v in violations)


@pytest.mark.unit
class TestShouldFailOnParseError:
    def test_should_fail_true_on_syntax_violation_at_error_threshold(self):
        """Parse errors fail the default error threshold."""
        validator = SqlValidator(dialect="postgres")

        result = ValidationResult(files_checked=1)
        result.add_violation(
            ValidationViolation(
                rule_id="parse_error",
                severity=ViolationSeverity.ERROR,
                message="Error tokenizing",
                source=ViolationSource.SYNTAX,
            )
        )

        assert validator.should_fail(result) is True

    def test_should_fail_false_on_syntax_violation_when_fail_on_never(self):
        validator = SqlValidator(dialect="postgres")
        validator.config.fail_on = "never"
        result = ValidationResult(files_checked=1)
        result.add_violation(
            ValidationViolation(
                rule_id="parse_error",
                severity=ViolationSeverity.ERROR,
                message="Error tokenizing",
                source=ViolationSource.SYNTAX,
            )
        )

        assert validator.should_fail(result) is False

    def test_should_fail_never_uses_serialized_source_values(self):
        validator = SqlValidator(dialect="postgres")
        validator.config.fail_on = "never"
        result = ValidationResult(files_checked=1)
        result.add_violation(
            ValidationViolation(
                rule_id="parse_error",
                severity=ViolationSeverity.ERROR,
                message="Error tokenizing",
                source=SimpleNamespace(value="syntax"),
            )
        )

        assert validator.should_fail(result) is False

    def test_should_fail_false_without_violations(self):
        validator = SqlValidator(dialect="postgres")
        result = ValidationResult(files_checked=1)

        assert validator.should_fail(result) is False

    def test_should_fail_false_for_business_rule_errors_when_disabled(self):
        """The unified threshold can explicitly disable finding-based failures."""
        validator = SqlValidator(dialect="postgres")
        validator.config.fail_on = "never"
        result = ValidationResult(files_checked=1)
        result.add_violation(
            ValidationViolation(
                rule_id="missing_where_clause",
                severity=ViolationSeverity.ERROR,
                message="UPDATE without WHERE",
                source=ViolationSource.PERFORMANCE,
            )
        )

        assert validator.should_fail(result) is False
