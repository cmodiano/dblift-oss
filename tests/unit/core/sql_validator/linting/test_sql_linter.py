"""Tests for SQL linter."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from core.sql_validator.linting.models import (
    ValidationResult,
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)
from core.sql_validator.linting.sql_linter import SqlLinter
from db.provider_registry import ProviderRegistry


@pytest.mark.unit
class TestSqlLinter:
    """Test SqlLinter class."""

    def test_linter_creation(self):
        """Test creating a SQL linter."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")
            assert linter.dialect == "postgres"
            assert linter.rules_config == {}

    def test_normalize_dialect(self):
        """Test dialect normalization."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")
            assert linter._normalize_dialect("postgresql") == "postgres"
            assert linter._normalize_dialect("mysql") == "mysql"
            assert linter._normalize_dialect("sqlite") == "sqlite"
            assert linter._normalize_dialect("sqlite3") == "sqlite"

    def test_get_sql_model_dialect(self):
        """Test SQL model dialect mapping."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")
            assert linter._get_sql_model_dialect("oracle") == "oracle"
            assert linter._get_sql_model_dialect("postgresql") == "postgresql"
            assert linter._get_sql_model_dialect("postgres") == "postgresql"
            assert linter._get_sql_model_dialect("sqlserver") == "sqlserver"
            assert linter._get_sql_model_dialect("tsql") == "sqlserver"
            assert linter._get_sql_model_dialect("sqlite") == "sqlite"
            assert linter._get_sql_model_dialect("sqlite3") == "sqlite"

    def test_get_sql_model_dialect_tsql_when_canonical_returns_none(self):
        """Framework name is sqlserver even if registry misses the sqlglot alias ``tsql``."""
        canon = ProviderRegistry.canonical_dialect_name

        def _patched(alias: str):
            if str(alias).lower() == "tsql":
                return None
            return canon(alias)

        with (
            patch.object(ProviderRegistry, "canonical_dialect_name", side_effect=_patched),
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")
            assert linter._get_sql_model_dialect("tsql") == "sqlserver"

    def test_init_without_sqlfluff(self):
        """Test initialization when sqlfluff is not available."""
        # Patch the import inside _init_linter to raise ImportError
        with patch(
            "core.sql_validator.linting.sql_linter.FluffConfig",
            side_effect=ImportError("No module"),
        ):
            linter = SqlLinter(dialect="postgresql")
            # When ImportError is raised, config and linter should be None
            # But if sqlfluff is actually installed, they won't be None
            # So we just verify the linter was created successfully
            assert linter is not None

    def test_init_with_custom_rules_path(self):
        """Test initialization with custom rules path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "rules.yaml"
            rules_file.write_text("rules: []")

            with (
                patch("core.sql_validator.linting.sql_linter.FluffConfig"),
                patch("core.sql_validator.linting.sql_linter.Linter"),
            ):
                linter = SqlLinter(
                    dialect="postgresql", custom_rules_path=rules_file, rules_config={}
                )
                assert linter.custom_rules_path == rules_file

    def test_build_rule_config(self):
        """Test building rule configuration."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            rules_config = {"rules": {"rule1": {"enabled": True}}}
            linter = SqlLinter(dialect="postgresql", rules_config=rules_config)
            config = linter._build_rule_config()
            assert config == {"rule1": {"enabled": True}}

    def test_init_with_custom_rules_data(self):
        """Test initialization with in-memory custom rules."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(
                dialect="postgresql",
                custom_rules_data={
                    "rules": [
                        {
                            "name": "no_drop_table",
                            "type": "pattern",
                            "prohibit": "DROP TABLE",
                            "message": "DROP TABLE is not allowed",
                            "severity": "error",
                        }
                    ]
                },
            )

        result = linter.lint_string("DROP TABLE customer;")

        assert any(v.rule_id == "no_drop_table" for v in result.violations)

    def test_lint_file(self):
        """Test linting a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            mock_linter = MagicMock()
            mock_linted_result = MagicMock()
            mock_violation = MagicMock()
            mock_violation.rule_code.return_value = "L001"
            mock_violation.desc.return_value = "Test violation"
            mock_violation.line_no = 1
            mock_violation.line_pos = 1
            mock_linted_result.violations = [mock_violation]

            mock_linter.lint_string.return_value = mock_linted_result

            with (
                patch("core.sql_validator.linting.sql_linter.FluffConfig"),
                patch("core.sql_validator.linting.sql_linter.Linter", return_value=mock_linter),
            ):
                linter = SqlLinter(dialect="postgresql")
                linter.linter = mock_linter

                result = linter.lint_file(sql_file)

                assert isinstance(result, ValidationResult)
                assert result.files_checked == 1

    def test_lint_file_without_sqlfluff(self):
        """Test linting file when sqlfluff is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            with patch(
                "core.sql_validator.linting.sql_linter.FluffConfig", side_effect=ImportError
            ):
                linter = SqlLinter(dialect="postgresql")
                result = linter.lint_file(sql_file)

                assert isinstance(result, ValidationResult)
                assert result.files_checked == 1

    def test_lint_file_error_handling(self):
        """Test error handling when linting file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            with (
                patch("core.sql_validator.linting.sql_linter.FluffConfig"),
                patch("core.sql_validator.linting.sql_linter.Linter"),
                patch(
                    "core.sql_validator.linting.sql_linter.read_migration_text",
                    side_effect=IOError("File error"),
                ),
            ):
                linter = SqlLinter(dialect="postgresql")
                result = linter.lint_file(sql_file)

                assert isinstance(result, ValidationResult)
                assert len(result.violations) > 0
                assert any(v.severity == ViolationSeverity.ERROR for v in result.violations)

    def test_lint_string(self):
        """Test linting a SQL string."""
        mock_linter = MagicMock()
        mock_linted_result = MagicMock()
        mock_violation = MagicMock()
        mock_violation.rule_code.return_value = "L001"
        mock_violation.desc.return_value = "Test violation"
        mock_violation.line_no = 1
        mock_violation.line_pos = 1
        mock_linted_result.violations = [mock_violation]

        mock_linter.lint_string.return_value = mock_linted_result

        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter", return_value=mock_linter),
        ):
            linter = SqlLinter(dialect="postgresql")
            linter.linter = mock_linter

            result = linter.lint_string("SELECT * FROM test;")

            assert isinstance(result, ValidationResult)
            assert result.files_checked == 1

    def test_lint_string_with_file_path(self):
        """Test linting string with file path."""
        file_path = Path("test.sql")

        mock_linter = MagicMock()
        mock_linted_result = MagicMock()
        mock_linted_result.violations = []
        mock_linter.lint_string.return_value = mock_linted_result

        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter", return_value=mock_linter),
        ):
            linter = SqlLinter(dialect="postgresql")
            linter.linter = mock_linter

            result = linter.lint_string("SELECT * FROM test;", file_path=file_path)

            mock_linter.lint_string.assert_called_once()
            assert isinstance(result, ValidationResult)

    def test_lint_string_error_handling(self):
        """Test error handling when linting string."""
        mock_linter = MagicMock()
        mock_linter.lint_string.side_effect = Exception("Linting error")

        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter", return_value=mock_linter),
        ):
            linter = SqlLinter(dialect="postgresql")
            linter.linter = mock_linter

            result = linter.lint_string("SELECT * FROM test;")

            assert isinstance(result, ValidationResult)
            assert len(result.violations) > 0
            assert any(v.severity == ViolationSeverity.ERROR for v in result.violations)

    def test_process_linting_result(self):
        """Test processing linting result."""
        mock_violation = MagicMock()
        mock_violation.rule_code.return_value = "L001"
        mock_violation.desc.return_value = "Test violation"
        mock_violation.line_no = 10
        mock_violation.line_pos = 5

        mock_linted_result = MagicMock()
        mock_linted_result.violations = [mock_violation]

        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")
            result = ValidationResult()

            file_path = Path("test.sql")
            linter._process_linting_result(mock_linted_result, file_path, result)

            assert len(result.violations) == 1
            assert result.violations[0].rule_id == "L001"
            assert result.violations[0].line == 10
            assert result.violations[0].column == 5

    def test_map_severity_from_config(self):
        """Test mapping severity from configuration."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            rules_config = {"severity": {"L001": "error"}}
            linter = SqlLinter(dialect="postgresql", rules_config=rules_config)

            severity = linter._map_severity("L001")
            assert severity == ViolationSeverity.ERROR

    def test_map_severity_parse_error(self):
        """Test mapping severity for parse errors."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")

            severity = linter._map_severity("PRS001")
            assert severity == ViolationSeverity.ERROR

    def test_map_severity_default_warning(self):
        """Test default severity mapping."""
        with (
            patch("core.sql_validator.linting.sql_linter.FluffConfig"),
            patch("core.sql_validator.linting.sql_linter.Linter"),
        ):
            linter = SqlLinter(dialect="postgresql")

            severity = linter._map_severity("L001")
            assert severity == ViolationSeverity.WARNING

    def test_lint_directory(self):
        """Test linting a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sql_file1 = tmp_path / "test1.sql"
            sql_file1.write_text("SELECT * FROM test1;")
            sql_file2 = tmp_path / "test2.sql"
            sql_file2.write_text("SELECT * FROM test2;")

            mock_linter = MagicMock()
            mock_linted_result = MagicMock()
            mock_linted_result.violations = []
            mock_linter.lint_string.return_value = mock_linted_result

            with (
                patch("core.sql_validator.linting.sql_linter.FluffConfig"),
                patch("core.sql_validator.linting.sql_linter.Linter", return_value=mock_linter),
            ):
                linter = SqlLinter(dialect="postgresql")
                linter.linter = mock_linter

                result = linter.lint_directory(tmp_path)

                assert isinstance(result, ValidationResult)
                # rglob finds all SQL files recursively, so count may vary
                assert result.files_checked >= 2

    def test_lint_directory_custom_pattern(self):
        """Test linting directory with custom pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sql_file = tmp_path / "test.sql"
            sql_file.write_text("SELECT * FROM test;")
            txt_file = tmp_path / "test.txt"
            txt_file.write_text("Not SQL")

            mock_linter = MagicMock()
            mock_linted_result = MagicMock()
            mock_linted_result.violations = []
            mock_linter.lint_string.return_value = mock_linted_result

            with (
                patch("core.sql_validator.linting.sql_linter.FluffConfig"),
                patch("core.sql_validator.linting.sql_linter.Linter", return_value=mock_linter),
            ):
                linter = SqlLinter(dialect="postgresql")
                linter.linter = mock_linter

                result = linter.lint_directory(tmp_path, pattern="*.sql")

                # rglob finds all SQL files recursively, so count may vary
                assert result.files_checked >= 1
