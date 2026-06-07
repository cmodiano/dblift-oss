"""BUG-07 regression: tokenizer failure must surface as validation FAILED.

Before ADR-0013 PR-3, ``_validate_sql_syntax`` caught any exception
from ``sql_analyzer.split_statements`` with a broad ``except Exception``,
fell back to ``validate_sql(script_content)`` on the whole file, and —
critically — recorded a failure only if the fallback returned
``(False, error)``. When the fallback returned ``(True, None)``
(tolerant PostgreSQL paths on ``$$``-quoted bodies were the skill
reproducer), the script was silently counted as a pass and
``validate-sql`` exited with "No issues found" over content the
tokenizer couldn't even parse.

These tests pin the new contract: a tokenizer/splitter failure IS a
validation failure, regardless of what the fallback returns.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.migration.migration import MigrationType
from core.migration.sql.sql_analyzer import SqlAnalyzer
from core.sql_validator.migration_validator import MigrationValidator, ValidationResult


def _make_validator_stub(sql_analyzer: MagicMock) -> MigrationValidator:
    validator = MigrationValidator.__new__(MigrationValidator)
    validator.log = MagicMock()
    validator.placeholders = {}
    validator.sql_analyzer = sql_analyzer
    quirks = MagicMock()
    quirks.supports_sqlplus_preprocessing = False
    validator._quirks = quirks
    return validator


def _make_script(
    content: str = "CREATE FUNCTION x() RETURNS INT AS $$ SELECT 1 $$;",
) -> SimpleNamespace:
    return SimpleNamespace(
        script_name="V1__create_fn.sql",
        content=content,
        type=MigrationType.SQL,
    )


@pytest.mark.unit
class TestValidateSqlSurfacesTokenizerErrors:
    def test_split_failure_with_tolerant_fallback_is_failure(self):
        """Tokenizer raises but whole-file fallback says OK — must still FAIL."""
        sql_analyzer = MagicMock()
        sql_analyzer.split_statements.side_effect = RuntimeError(
            "tokenizer error at $$-quoted body"
        )
        # The tolerant fallback on some dialect paths returns (True, None) for
        # content it couldn't actually parse. The fix must not accept that
        # as erasing the split failure.
        sql_analyzer.validate_sql.return_value = (True, None)

        validator = _make_validator_stub(sql_analyzer)
        result = ValidationResult()
        issues: list[str] = []
        script = _make_script()

        validator._validate_sql_syntax([script], result, issues)

        assert result.success is False, (
            "tokenizer failure must mark validation FAILED even if fallback "
            "tolerantly returned True"
        )
        assert any("V1__create_fn.sql" in issue for issue in issues)
        assert any("tokenizer error" in issue for issue in issues)

    def test_split_failure_with_failing_fallback_is_failure(self):
        """Defensive: if the fallback also fails, we still have one primary failure."""
        sql_analyzer = MagicMock()
        sql_analyzer.split_statements.side_effect = RuntimeError("split blew up")
        sql_analyzer.validate_sql.return_value = (False, "parse error at line 3")

        validator = _make_validator_stub(sql_analyzer)
        result = ValidationResult()
        issues: list[str] = []
        script = _make_script()

        validator._validate_sql_syntax([script], result, issues)

        assert result.success is False
        assert any("V1__create_fn.sql" in issue for issue in issues)
        # Primary error carries the split-failure message.
        assert result.error_message
        assert "split blew up" in result.error_message

    def test_split_success_then_happy_path_keeps_result_successful(self):
        """No behaviour change on the happy path (sanity check)."""
        sql_analyzer = MagicMock()
        sql_analyzer.split_statements.return_value = ["SELECT 1;"]
        sql_analyzer.validate_sql.return_value = (True, None)
        sql_analyzer.analyze_statement.return_value = {"type": "query", "objects": []}

        validator = _make_validator_stub(sql_analyzer)
        result = ValidationResult()
        issues: list[str] = []
        script = _make_script()

        validator._validate_sql_syntax([script], result, issues)

        assert result.success is True
        assert issues == []
        sql_analyzer.split_statements.assert_called_once_with(
            "CREATE FUNCTION x() RETURNS INT AS $$ SELECT 1 $$;",
            strict_tokenizer=True,
        )

    def test_tokenizer_warning_becomes_validation_failure_in_strict_mode(self):
        """Production validation promotes tokenizer unknown-character warnings to failure."""
        validator = _make_validator_stub(SqlAnalyzer(dialect="postgresql"))
        result = ValidationResult()
        issues: list[str] = []
        script = _make_script("SELECT §;")

        validator._validate_sql_syntax([script], result, issues)

        assert result.success is False
        assert result.error_message
        assert any("Tokenizer (postgresql)" in issue for issue in issues)
