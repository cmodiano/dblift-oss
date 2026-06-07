"""Tests for SQL validator."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config.validation_config import ValidationConfig
from core.sql_validator.linting.models import (
    ValidationResult,
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)
from core.sql_validator.linting.sql_validator import SqlValidator


@pytest.mark.unit
class TestSqlValidator:
    """Test SqlValidator class."""

    def test_validator_creation(self):
        """Test creating a SQL validator."""
        validator = SqlValidator(dialect="postgresql")
        assert validator.dialect == "postgresql"
        assert isinstance(validator.config, ValidationConfig)

    def test_validator_creation_with_config(self):
        """Test creating validator with custom config."""
        config = ValidationConfig()
        validator = SqlValidator(dialect="postgresql", validation_config=config)
        assert validator.config == config

    def test_validator_with_rules_file(self):
        """Test validator initialization with rules file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "rules.yaml"
            rules_file.write_text("rules: []")

            config = ValidationConfig()
            config.enabled = True
            config.rules_file = str(rules_file)

            validator = SqlValidator(dialect="postgresql", validation_config=config)
            # Linter must be initialized when rules file exists and config is enabled
            assert validator.linter is not None

    def test_validator_without_rules_file(self):
        """Test validator initialization without rules file."""
        config = ValidationConfig()
        config.enabled = True
        config.rules_file = None

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        # Linter must be None when no rules file provided
        assert validator.linter is None

    def test_validator_with_rule_selection(self, tmp_path):
        """Test validator initialization with selected built-in rules."""
        sql_file = tmp_path / "V1__grant.sql"
        sql_file.write_text("GRANT ALL PRIVILEGES ON customer TO app_user;")
        config = ValidationConfig(rules=["no_grant_all_privileges"], severity_threshold="info")

        validator = SqlValidator("postgresql", config)
        result = validator.validate_file(sql_file)

        assert any(v.rule_id == "no_grant_all_privileges" for v in result.violations)

    def test_validator_with_performance_enabled(self):
        """Test validator with performance analysis enabled."""
        config = ValidationConfig()
        config.enabled = True
        config.performance_enabled = True

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        assert validator.performance_analyzer is not None

    def test_validator_with_performance_disabled(self):
        """Test validator with performance analysis disabled."""
        config = ValidationConfig()
        config.enabled = True
        config.performance_enabled = False

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        assert validator.performance_analyzer is None

    def test_validate_file_disabled(self):
        """Test validation when disabled."""
        config = ValidationConfig()
        config.enabled = False

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            result = validator.validate_file(sql_file)

            assert isinstance(result, ValidationResult)
            assert result.files_checked == 1
            assert len(result.violations) == 0

    def test_validate_file_excluded(self):
        """Test validation of excluded file."""
        config = ValidationConfig()
        config.enabled = True
        config.exclude_patterns = ["*test*"]

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            result = validator.validate_file(sql_file)

            assert isinstance(result, ValidationResult)
            assert len(result.violations) == 0

    def test_validate_file_with_linter(self):
        """Test validation with linter."""
        config = ValidationConfig()
        config.enabled = True

        mock_linter = MagicMock()
        mock_result = ValidationResult(files_checked=1)
        mock_result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.WARNING,
                message="Test violation",
            )
        )
        mock_linter.lint_file.return_value = mock_result

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        validator.linter = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            result = validator.validate_file(sql_file)

            assert isinstance(result, ValidationResult)
            assert len(result.violations) >= 1

    def test_validate_file_with_performance_analyzer(self):
        """Test validation with performance analyzer."""
        config = ValidationConfig()
        config.enabled = True
        config.performance_enabled = True

        mock_perf_analyzer = MagicMock()
        mock_violation = ValidationViolation(
            rule_id="perf1",
            severity=ViolationSeverity.WARNING,
            message="Performance issue",
            source=ViolationSource.PERFORMANCE,
        )
        mock_perf_analyzer.analyze_statements.return_value = [mock_violation]

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        validator.performance_analyzer = mock_perf_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            result = validator.validate_file(sql_file)

            assert isinstance(result, ValidationResult)
            assert len(result.violations) >= 1
            mock_perf_analyzer.analyze_statements.assert_called_once()
            statements = mock_perf_analyzer.analyze_statements.call_args.args[0]
            assert statements == ["SELECT * FROM test;"]

    def test_performance_analysis_receives_only_relevant_statements(self):
        """DDL/procedural SQL is filtered before performance analysis."""
        config = ValidationConfig()
        config.enabled = True
        config.performance_enabled = True

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        mock_perf_analyzer = MagicMock()
        mock_perf_analyzer.analyze_statements.return_value = []
        validator.performance_analyzer = mock_perf_analyzer

        sql = """
        CREATE TABLE dblift_test.orders (id INT, status TEXT);
        CREATE FUNCTION dblift_test.touch_order() RETURNS trigger AS $$
        BEGIN
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        DROP TRIGGER IF EXISTS trg_orders_insert ON dblift_test.orders;
        SELECT * FROM dblift_test.orders;
        UPDATE dblift_test.orders SET status = 'done';
        DELETE FROM dblift_test.orders;
        INSERT INTO dblift_test.orders(id, status) VALUES (1, 'pending');
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text(sql)

            validator.validate_file(sql_file)

        mock_perf_analyzer.analyze_statements.assert_called_once()
        statements = mock_perf_analyzer.analyze_statements.call_args.args[0]
        assert len(statements) == 3
        assert [statement.strip().split()[0].upper() for statement in statements] == [
            "SELECT",
            "UPDATE",
            "DELETE",
        ]

    def test_validate_file_error_handling(self):
        """Test error handling during validation."""
        config = ValidationConfig()
        config.enabled = True

        mock_linter = MagicMock()
        mock_linter.lint_file.side_effect = Exception("Linting error")

        validator = SqlValidator(dialect="postgresql", validation_config=config)
        validator.linter = mock_linter

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            result = validator.validate_file(sql_file)

            assert isinstance(result, ValidationResult)

    def test_validate_files(self):
        """Test validating multiple files."""
        config = ValidationConfig()
        config.enabled = True

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file1 = Path(tmpdir) / "test1.sql"
            sql_file1.write_text("SELECT * FROM test1;")
            sql_file2 = Path(tmpdir) / "test2.sql"
            sql_file2.write_text("SELECT * FROM test2;")

            result = validator.validate_files([sql_file1, sql_file2])

            assert isinstance(result, ValidationResult)

    def test_validate_directory(self):
        """Test validating directory."""
        config = ValidationConfig()
        config.enabled = True

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sql_file1 = tmp_path / "test1.sql"
            sql_file1.write_text("SELECT * FROM test1;")
            sql_file2 = tmp_path / "test2.sql"
            sql_file2.write_text("SELECT * FROM test2;")

            result = validator.validate_directory(tmp_path)

            assert isinstance(result, ValidationResult)

    def test_validate_directory_non_recursive(self):
        """Test validating directory non-recursively."""
        config = ValidationConfig()
        config.enabled = True

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sql_file = tmp_path / "test.sql"
            sql_file.write_text("SELECT * FROM test;")

            subdir = tmp_path / "subdir"
            subdir.mkdir()
            sub_sql_file = subdir / "sub.sql"
            sub_sql_file.write_text("SELECT * FROM sub;")

            result = validator.validate_directory(tmp_path, recursive=False)

            assert isinstance(result, ValidationResult)

    def test_validate_directory_custom_pattern(self):
        """Test validating directory with custom pattern."""
        config = ValidationConfig()
        config.enabled = True

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sql_file = tmp_path / "test.sql"
            sql_file.write_text("SELECT * FROM test;")
            txt_file = tmp_path / "test.txt"
            txt_file.write_text("Not SQL")

            result = validator.validate_directory(tmp_path, pattern="*.sql")

            assert isinstance(result, ValidationResult)

    def test_should_exclude(self):
        """Test file exclusion logic."""
        config = ValidationConfig()
        config.exclude_patterns = ["*test*", "*temp*"]

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        assert validator._should_exclude(Path("test.sql")) is True
        assert validator._should_exclude(Path("temp.sql")) is True
        assert validator._should_exclude(Path("valid.sql")) is False

    def test_filter_by_severity(self):
        """Test filtering violations by severity."""
        config = ValidationConfig()
        config.severity_threshold = "warning"

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        result = ValidationResult()
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error",
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2",
                severity=ViolationSeverity.WARNING,
                message="Warning",
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule3",
                severity=ViolationSeverity.INFO,
                message="Info",
            )
        )

        filtered = validator._filter_by_severity(result)

        assert len(filtered.violations) == 2  # ERROR and WARNING, not INFO

    def test_filter_by_severity_error_threshold(self):
        """Test filtering with error threshold."""
        config = ValidationConfig()
        config.severity_threshold = "error"

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        result = ValidationResult()
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error",
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2",
                severity=ViolationSeverity.WARNING,
                message="Warning",
            )
        )

        filtered = validator._filter_by_severity(result)

        assert len(filtered.violations) == 1  # Only ERROR

    def test_should_fail_with_errors(self):
        """Test should_fail when errors present."""
        config = ValidationConfig(fail_on="error")

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        result = ValidationResult()
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error",
            )
        )

        assert validator.should_fail(result) is True

    def test_should_fail_with_warnings(self):
        """Test should_fail when warnings are present."""
        config = ValidationConfig(fail_on="warning")

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        result = ValidationResult()
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.WARNING,
                message="Warning",
            )
        )

        assert validator.should_fail(result) is True

    def test_should_fail_never(self):
        """Test should_fail when finding failure is disabled."""
        config = ValidationConfig(fail_on="never")

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        result = ValidationResult()
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error",
            )
        )

        assert validator.should_fail(result) is False

    def test_should_fail_error_threshold_ignores_warnings(self):
        """Test should_fail with the default error threshold."""
        config = ValidationConfig(fail_on="error")

        validator = SqlValidator(dialect="postgresql", validation_config=config)

        result = ValidationResult()
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.WARNING,
                message="Warning",
            )
        )

        assert validator.should_fail(result) is False
