"""Tests for SQL validation models."""

from pathlib import Path

import pytest

from core.sql_validator.linting.models import (
    ValidationResult,
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)


@pytest.mark.unit
class TestViolationSeverity:
    """Test ViolationSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert ViolationSeverity.ERROR.value == "error"
        assert ViolationSeverity.WARNING.value == "warning"
        assert ViolationSeverity.INFO.value == "info"


@pytest.mark.unit
class TestViolationSource:
    """Test ViolationSource enum."""

    def test_source_values(self):
        """Test source enum values."""
        assert ViolationSource.BUSINESS_RULE.value == "business_rule"
        assert ViolationSource.PERFORMANCE.value == "performance"
        assert ViolationSource.SYNTAX.value == "syntax"


@pytest.mark.unit
class TestValidationViolation:
    """Test ValidationViolation dataclass."""

    def test_violation_creation(self):
        """Test creating a validation violation."""
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.ERROR,
            message="Test violation",
        )

        assert violation.rule_id == "test_rule"
        assert violation.severity == ViolationSeverity.ERROR
        assert violation.message == "Test violation"
        assert violation.file_path is None
        assert violation.line is None
        assert violation.column is None
        assert violation.source == ViolationSource.BUSINESS_RULE
        assert violation.suggestion is None
        assert violation.code_snippet is None

    def test_violation_with_all_fields(self):
        """Test violation with all fields populated."""
        file_path = Path("test.sql")
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.WARNING,
            message="Test violation",
            file_path=file_path,
            line=10,
            column=5,
            source=ViolationSource.SYNTAX,
            suggestion="Fix this",
            code_snippet="SELECT * FROM test;",
        )

        assert violation.file_path == file_path
        assert violation.line == 10
        assert violation.column == 5
        assert violation.source == ViolationSource.SYNTAX
        assert violation.suggestion == "Fix this"
        assert violation.code_snippet == "SELECT * FROM test;"

    def test_violation_to_dict(self):
        """Test converting violation to dictionary."""
        file_path = Path("test.sql")
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.ERROR,
            message="Test violation",
            file_path=file_path,
            line=10,
            column=5,
            source=ViolationSource.PERFORMANCE,
            suggestion="Fix this",
            code_snippet="SELECT * FROM test;",
        )

        result = violation.to_dict()

        assert result["rule_id"] == "test_rule"
        assert result["severity"] == "error"
        assert result["message"] == "Test violation"
        assert result["file_path"] == "test.sql"
        assert result["line"] == 10
        assert result["column"] == 5
        assert result["source"] == "performance"
        assert result["suggestion"] == "Fix this"
        assert result["code_snippet"] == "SELECT * FROM test;"

    def test_violation_to_dict_no_file(self):
        """Test converting violation to dict without file path."""
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.WARNING,
            message="Test violation",
        )

        result = violation.to_dict()
        assert result["file_path"] is None

    def test_violation_str_representation(self):
        """Test string representation of violation."""
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.ERROR,
            message="Test violation",
        )

        result = str(violation)
        assert "❌" in result
        assert "Test violation" in result

    def test_violation_str_with_file(self):
        """Test string representation with file path."""
        file_path = Path("test.sql")
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.WARNING,
            message="Test violation",
            file_path=file_path,
        )

        result = str(violation)
        assert "test.sql" in result
        assert "⚠️" in result

    def test_violation_str_with_line_column(self):
        """Test string representation with line and column."""
        file_path = Path("test.sql")
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.INFO,
            message="Test violation",
            file_path=file_path,
            line=10,
            column=5,
        )

        result = str(violation)
        assert "test.sql:10:5" in result
        assert "ℹ️" in result

    def test_violation_str_with_suggestion(self):
        """Test string representation with suggestion."""
        violation = ValidationViolation(
            rule_id="test_rule",
            severity=ViolationSeverity.ERROR,
            message="Test violation",
            suggestion="Fix this issue",
        )

        result = str(violation)
        assert "💡 Fix: Fix this issue" in result


@pytest.mark.unit
class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_result_creation(self):
        """Test creating a validation result."""
        result = ValidationResult()

        assert result.violations == []
        assert result.files_checked == 0
        assert result.success is True

    def test_result_with_initial_values(self):
        """Test result with initial values."""
        result = ValidationResult(files_checked=5, success=False)

        assert result.files_checked == 5
        assert result.success is False

    def test_error_count(self):
        """Test error count property."""
        result = ValidationResult()

        result.violations.append(
            ValidationViolation(
                rule_id="rule1", severity=ViolationSeverity.ERROR, message="Error 1"
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2", severity=ViolationSeverity.WARNING, message="Warning 1"
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule3", severity=ViolationSeverity.ERROR, message="Error 2"
            )
        )

        assert result.error_count == 2

    def test_warning_count(self):
        """Test warning count property."""
        result = ValidationResult()

        result.violations.append(
            ValidationViolation(
                rule_id="rule1", severity=ViolationSeverity.WARNING, message="Warning 1"
            )
        )
        result.violations.append(
            ValidationViolation(rule_id="rule2", severity=ViolationSeverity.INFO, message="Info 1")
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule3", severity=ViolationSeverity.WARNING, message="Warning 2"
            )
        )

        assert result.warning_count == 2

    def test_info_count(self):
        """Test info count property."""
        result = ValidationResult()

        result.violations.append(
            ValidationViolation(rule_id="rule1", severity=ViolationSeverity.INFO, message="Info 1")
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2", severity=ViolationSeverity.ERROR, message="Error 1"
            )
        )

        assert result.info_count == 1

    def test_has_violations(self):
        """Test has_violations property."""
        result = ValidationResult()
        assert result.has_violations is False

        result.violations.append(
            ValidationViolation(
                rule_id="rule1", severity=ViolationSeverity.WARNING, message="Warning"
            )
        )
        assert result.has_violations is True

    def test_has_errors(self):
        """Test has_errors property."""
        result = ValidationResult()
        assert result.has_errors is False

        result.violations.append(
            ValidationViolation(
                rule_id="rule1", severity=ViolationSeverity.WARNING, message="Warning"
            )
        )
        assert result.has_errors is False

        result.violations.append(
            ValidationViolation(rule_id="rule2", severity=ViolationSeverity.ERROR, message="Error")
        )
        assert result.has_errors is True

    def test_add_violation(self):
        """Test adding a violation."""
        result = ValidationResult()

        violation = ValidationViolation(
            rule_id="test_rule", severity=ViolationSeverity.WARNING, message="Test"
        )
        result.add_violation(violation)

        assert len(result.violations) == 1
        assert result.violations[0] == violation

    def test_add_violation_error_sets_success_false(self):
        """Test that adding an error violation sets success to False."""
        result = ValidationResult()
        assert result.success is True

        violation = ValidationViolation(
            rule_id="test_rule", severity=ViolationSeverity.ERROR, message="Error"
        )
        result.add_violation(violation)

        assert result.success is False

    def test_add_violation_warning_keeps_success(self):
        """Test that adding a warning violation doesn't change success."""
        result = ValidationResult()
        assert result.success is True

        violation = ValidationViolation(
            rule_id="test_rule", severity=ViolationSeverity.WARNING, message="Warning"
        )
        result.add_violation(violation)

        assert result.success is True

    def test_merge_results(self):
        """Test merging two validation results."""
        result1 = ValidationResult(files_checked=2)
        result1.violations.append(
            ValidationViolation(rule_id="rule1", severity=ViolationSeverity.ERROR, message="Error")
        )

        result2 = ValidationResult(files_checked=3)
        result2.violations.append(
            ValidationViolation(
                rule_id="rule2", severity=ViolationSeverity.WARNING, message="Warning"
            )
        )

        result1.merge(result2)

        assert len(result1.violations) == 2
        assert result1.files_checked == 5

    def test_merge_results_with_failure(self):
        """Test merging results where other result failed."""
        result1 = ValidationResult(success=True)
        result2 = ValidationResult(success=False)

        result1.merge(result2)

        assert result1.success is False

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = ValidationResult(files_checked=2)
        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error message",
                file_path=Path("test.sql"),
                line=10,
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2",
                severity=ViolationSeverity.WARNING,
                message="Warning message",
            )
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["files_checked"] == 2
        assert len(result_dict["violations"]) == 2
        assert result_dict["summary"]["total"] == 2
        assert result_dict["summary"]["errors"] == 1
        assert result_dict["summary"]["warnings"] == 1
        assert result_dict["summary"]["info"] == 0

    def test_get_violations_by_source(self):
        """Test getting violations by source."""
        result = ValidationResult()

        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error",
                source=ViolationSource.BUSINESS_RULE,
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2",
                severity=ViolationSeverity.WARNING,
                message="Warning",
                source=ViolationSource.PERFORMANCE,
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule3",
                severity=ViolationSeverity.INFO,
                message="Info",
                source=ViolationSource.BUSINESS_RULE,
            )
        )

        business_rules = result.get_violations_by_source(ViolationSource.BUSINESS_RULE)
        assert len(business_rules) == 2

        performance = result.get_violations_by_source(ViolationSource.PERFORMANCE)
        assert len(performance) == 1

    def test_get_violations_by_file(self):
        """Test getting violations by file."""
        result = ValidationResult()

        file1 = Path("test1.sql")
        file2 = Path("test2.sql")

        result.violations.append(
            ValidationViolation(
                rule_id="rule1",
                severity=ViolationSeverity.ERROR,
                message="Error",
                file_path=file1,
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule2",
                severity=ViolationSeverity.WARNING,
                message="Warning",
                file_path=file2,
            )
        )
        result.violations.append(
            ValidationViolation(
                rule_id="rule3",
                severity=ViolationSeverity.INFO,
                message="Info",
                file_path=file1,
            )
        )

        file1_violations = result.get_violations_by_file(file1)
        assert len(file1_violations) == 2

        file2_violations = result.get_violations_by_file(file2)
        assert len(file2_violations) == 1
