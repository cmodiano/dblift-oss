"""Oracle validate-sql preprocessing regressions."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from config.validation_config import ValidationConfig
from core.sql_validator.linting.performance_analyzer import PerformanceAnalyzer
from core.sql_validator.linting.sql_validator import SqlValidator


@pytest.mark.unit
class TestOracleValidateSqlPreprocessing:
    def _validate_sql(self, sql: str):
        config = ValidationConfig()
        config.enabled = True
        config.performance_enabled = True
        validator = SqlValidator(dialect="oracle", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text(sql)
            return validator.validate_file(sql_file).violations

    def test_sqlplus_directives_and_plsql_blocks_do_not_emit_parse_errors(self):
        sql = """
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET SERVEROUTPUT ON
@ /tmp/other_script.sql
CREATE OR REPLACE PROCEDURE p AS
BEGIN
  NULL;
END;
/
CREATE TABLE t_oracle_validate (id NUMBER);
"""

        violations = self._validate_sql(sql)

        assert not any(v.rule_id == "parse_error" for v in violations)

    def test_oracle_text_index_is_skipped_by_sqlglot_analysis(self):
        sql = """
CREATE INDEX idx_docs_text ON docs(content)
  INDEXTYPE IS CTXSYS.CONTEXT
  PARAMETERS ('lexer my_lexer');
"""

        violations = self._validate_sql(sql)

        assert not any(v.rule_id == "parse_error" for v in violations)

    def test_plain_oracle_sql_still_gets_performance_checks(self):
        analyzer = PerformanceAnalyzer(dialect="oracle")

        violations = analyzer.analyze_sql("DELETE FROM audit_log;", Path("V3__delete.sql"))

        assert any(v.rule_id == "missing_where_clause" for v in violations)
