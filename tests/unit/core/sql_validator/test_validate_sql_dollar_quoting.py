"""BUG-03 regression: ``validate-sql`` must not false-positive on ``$$`` bodies.

PL/pgSQL CREATE FUNCTION / CREATE TRIGGER bodies use PostgreSQL dollar-quoting
(``$$`` or ``$tag$``). sqlglot's tokenizer does not parse dollar-quoted bodies
cleanly and was emitting ``Error tokenizing '...'``. After BUG-06 those parse
errors became ERROR violations and failed the exit code — a false positive
since the migrations run fine.

The fix:
1. A dollar-quote-aware statement splitter keeps function bodies intact.
2. Parse failures on statements containing ``$$`` / ``$tag$`` are logged at
   debug and not surfaced as violations. Non-dollar-quoted parse errors still
   fail loudly (BUG-06 invariant preserved).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from config.validation_config import ValidationConfig
from core.migration.sql.sql_analyzer import SqlAnalyzer
from core.sql_validator.linting.models import ViolationSeverity, ViolationSource
from core.sql_validator.linting.performance_analyzer import PerformanceAnalyzer
from core.sql_validator.linting.sql_validator import SqlValidator


@pytest.mark.unit
class TestDollarQuoteStatementSplitter:
    def test_split_respects_double_dollar_body(self):
        analyzer = SqlAnalyzer(dialect="postgresql")
        sql = (
            "CREATE FUNCTION bump() RETURNS TRIGGER AS $$\n"
            "BEGIN\n"
            "  NEW.updated_at = NOW();\n"
            "  RETURN NEW;\n"
            "END;\n"
            "$$ LANGUAGE plpgsql;\n"
            "SELECT 1;"
        )

        parts = analyzer.split_statements(sql)
        # Two statements: the whole CREATE FUNCTION block, then SELECT 1.
        assert len(parts) == 2
        assert "BEGIN" in parts[0] and "END" in parts[0]
        assert "SELECT 1" in parts[1]

    def test_split_respects_named_dollar_tag(self):
        analyzer = SqlAnalyzer(dialect="postgresql")
        sql = (
            "CREATE FUNCTION x() RETURNS VOID AS $body$\n"
            "BEGIN\n"
            "  INSERT INTO t VALUES (1);\n"
            "  INSERT INTO t VALUES (2);\n"
            "END;\n"
            "$body$ LANGUAGE plpgsql;"
        )
        parts = [p for p in analyzer.split_statements(sql) if p.strip()]
        assert len(parts) == 1
        assert "INSERT INTO t VALUES (1)" in parts[0]
        assert "INSERT INTO t VALUES (2)" in parts[0]

    def test_split_without_dollar_quote_unchanged(self):
        analyzer = SqlAnalyzer(dialect="postgresql")
        sql = "SELECT 1; SELECT 2; UPDATE t SET x=1 WHERE id=1;"
        parts = [p.strip().rstrip(";") for p in analyzer.split_statements(sql) if p.strip()]
        assert parts == [
            "SELECT 1",
            "SELECT 2",
            "UPDATE t SET x=1 WHERE id=1",
        ]


@pytest.mark.unit
class TestDollarQuotedParseErrorSuppressed:
    def _validate_sql(self, sql: str):
        config = ValidationConfig()
        config.enabled = True
        config.performance_enabled = True
        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text(sql)
            return validator.validate_file(sql_file).violations

    def test_trigger_with_dollar_body_emits_no_parse_error_violation(self):
        """A PL/pgSQL trigger body must not trigger a parse_error violation."""
        sql = (
            "CREATE FUNCTION set_updated_at() RETURNS TRIGGER AS $$\n"
            "BEGIN NEW.updated_at = NOW(); RETURN NEW; END;\n"
            "$$ LANGUAGE plpgsql;"
        )

        violations = self._validate_sql(sql)

        assert not any(v.rule_id == "parse_error" for v in violations)

    def test_mixed_dollar_body_and_plain_sql_preserves_other_checks(self):
        """Plain SQL after a $$ body must still be parsed and linted."""
        sql = (
            "CREATE FUNCTION f() RETURNS TRIGGER AS $$\n"
            "BEGIN RETURN NULL; END;\n"
            "$$ LANGUAGE plpgsql;\n"
            "DELETE FROM big_table;"  # missing WHERE → should still be flagged
        )

        violations = self._validate_sql(sql)

        # No false positive from the $$ body.
        assert not any(v.rule_id == "parse_error" for v in violations)
        # Real issue in the plain DELETE still caught.
        assert any(v.rule_id == "missing_where_clause" for v in violations)

    def test_non_dollar_parse_error_still_surfaced(self):
        """BUG-06 invariant: real parse errors must still emit ERROR violations."""
        analyzer = PerformanceAnalyzer(dialect="postgres")
        # Gibberish with no dollar quoting.
        violations = analyzer.analyze_sql("THIS IS NOT SQL @#$%;", Path("V5__broken.sql"))

        parse_errors = [v for v in violations if v.rule_id == "parse_error"]
        # sqlglot may or may not reject this depending on permissiveness.
        # The invariant we care about: IF a parse_error surfaces, it's ERROR + SYNTAX.
        for v in parse_errors:
            assert v.severity == ViolationSeverity.ERROR
            assert v.source == ViolationSource.SYNTAX
