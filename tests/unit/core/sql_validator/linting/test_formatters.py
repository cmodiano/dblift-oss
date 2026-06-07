"""Tests for SQL validation output formatters."""

import json
from pathlib import Path

import pytest

from core.sql_validator.linting.formatters import (
    CompactFormatter,
    ConsoleFormatter,
    FormatterFactory,
    GitHubActionsFormatter,
    GitLabFormatter,
    JSONFormatter,
    OutputFormatter,
    SarifFormatter,
)
from core.sql_validator.linting.models import (
    ValidationResult,
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)


@pytest.fixture
def empty_result():
    """ValidationResult with no violations."""
    return ValidationResult(violations=[], files_checked=5, success=True)


@pytest.fixture
def error_violation():
    return ValidationViolation(
        rule_id="BR001",
        severity=ViolationSeverity.ERROR,
        message="SELECT * is not allowed",
        file_path=Path("migrations/V1__init.sql"),
        line=10,
        column=5,
        source=ViolationSource.BUSINESS_RULE,
        suggestion="List columns explicitly",
    )


@pytest.fixture
def warning_violation():
    return ValidationViolation(
        rule_id="PERF001",
        severity=ViolationSeverity.WARNING,
        message="Missing index on foreign key",
        file_path=Path("migrations/V2__update.sql"),
        line=25,
        source=ViolationSource.PERFORMANCE,
    )


@pytest.fixture
def info_violation():
    return ValidationViolation(
        rule_id="SYN001",
        severity=ViolationSeverity.INFO,
        message="Trailing whitespace",
        file_path=None,
        line=None,
        source=ViolationSource.SYNTAX,
    )


@pytest.fixture
def result_with_violations(error_violation, warning_violation, info_violation):
    """ValidationResult with mixed violations."""
    result = ValidationResult(files_checked=3, success=False)
    result.violations = [error_violation, warning_violation, info_violation]
    return result


@pytest.mark.unit
class TestConsoleFormatter:
    """Tests for ConsoleFormatter."""

    def test_format_no_violations(self, empty_result):
        formatter = ConsoleFormatter()
        output = formatter.format(empty_result)

        assert "validate-sql findings" in output
        assert "Checked: 5" in output
        assert "No findings." in output
        assert "=" * 60 in output

    def test_format_with_violations(self, result_with_violations):
        formatter = ConsoleFormatter()
        output = formatter.format(result_with_violations)

        assert "Checked: 3" in output
        assert "Errors: 1" in output
        assert "Warnings: 1" in output
        assert "Info: 1" in output

    def test_format_violations_uses_codes(self, result_with_violations):
        formatter = ConsoleFormatter()
        output = formatter.format(result_with_violations)

        assert "ERROR [BR001]" in output
        assert "WARN [PERF001]" in output
        assert "INFO [SYN001]" in output

    def test_format_violations_grouped_by_file(self, result_with_violations):
        formatter = ConsoleFormatter()
        output = formatter.format(result_with_violations)

        assert "migrations/V1__init.sql" in output
        assert "migrations/V2__update.sql" in output
        assert "inline" in output

    def test_format_source_labels(self, result_with_violations):
        formatter = ConsoleFormatter()
        output = formatter.format(result_with_violations)

        assert "[Business Rule]" not in output
        assert "[Performance]" not in output
        assert "[Syntax]" not in output

    def test_format_violations_includes_violation_str(self, error_violation):
        result = ValidationResult(files_checked=1, success=False)
        result.violations = [error_violation]
        formatter = ConsoleFormatter()
        output = formatter.format(result)

        assert "SELECT * is not allowed" in output

    def test_is_output_formatter_subclass(self):
        assert issubclass(ConsoleFormatter, OutputFormatter)


@pytest.mark.unit
class TestJSONFormatter:
    """Tests for JSONFormatter."""

    def test_format_returns_valid_json(self, result_with_violations):
        formatter = JSONFormatter()
        output = formatter.format(result_with_violations)

        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_format_contains_to_dict_structure(self, result_with_violations):
        formatter = JSONFormatter()
        output = formatter.format(result_with_violations)
        parsed = json.loads(output)

        assert parsed["command"] == "validate-sql"
        assert "success" in parsed
        assert "checked_count" in parsed
        assert "findings" in parsed
        assert "summary" in parsed
        assert parsed["checked_count"] == 3
        assert parsed["success"] is False

    def test_format_summary_counts(self, result_with_violations):
        formatter = JSONFormatter()
        output = formatter.format(result_with_violations)
        parsed = json.loads(output)

        summary = parsed["summary"]
        assert summary["error"] == 1
        assert summary["warning"] == 1
        assert summary["info"] == 1

    def test_format_violations_detail(self, error_violation):
        result = ValidationResult(files_checked=1, success=False)
        result.violations = [error_violation]
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(result))

        v = parsed["findings"][0]
        assert v["code"] == "BR001"
        assert v["severity"] == "error"
        assert v["message"] == "SELECT * is not allowed"
        assert v["file"] == "migrations/V1__init.sql"
        assert v["line"] == 10
        assert v["details"]["source"] == "business_rule"
        assert v["details"]["suggestion"] == "List columns explicitly"

    def test_format_empty_result(self, empty_result):
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(empty_result))

        assert parsed["success"] is True
        assert parsed["findings"] == []
        assert parsed["summary"]["error"] == 0

    def test_format_uses_formatter_fail_on_threshold(self, warning_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [warning_violation]
        formatter = JSONFormatter(fail_on="warning")
        parsed = json.loads(formatter.format(result))

        assert parsed["fail_on"] == "warning"
        assert parsed["success"] is False

    def test_format_prefers_result_fail_on_threshold(self, warning_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [warning_violation]
        result.fail_on = "warning"
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(result))

        assert parsed["fail_on"] == "warning"
        assert parsed["success"] is False

    def test_is_output_formatter_subclass(self):
        assert issubclass(JSONFormatter, OutputFormatter)


@pytest.mark.unit
class TestCompactFormatter:
    """Tests for CompactFormatter."""

    def test_format_no_violations(self, empty_result):
        formatter = CompactFormatter()
        output = formatter.format(empty_result)

        assert output == "OK [validate-sql]: 5 checked, no findings"

    def test_format_error_violation(self, error_violation):
        result = ValidationResult(files_checked=1, success=False)
        result.violations = [error_violation]
        formatter = CompactFormatter()
        output = formatter.format(result)

        assert output.startswith("ERROR")
        assert "[BR001]" in output
        assert "migrations/V1__init.sql:10" in output
        assert "SELECT * is not allowed" in output

    def test_format_warning_violation(self, warning_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [warning_violation]
        formatter = CompactFormatter()
        output = formatter.format(result)

        assert "WARN" in output
        assert "[PERF001]" in output
        assert "migrations/V2__update.sql:25" in output

    def test_format_info_violation(self, info_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [info_violation]
        formatter = CompactFormatter()
        output = formatter.format(result)

        assert "INFO" in output
        assert "[SYN001]" in output
        assert "inline" in output
        # Location is "inline" with no line number suffix like ":5"
        assert ": inline: " in output

    def test_format_multiple_violations(self, result_with_violations):
        formatter = CompactFormatter()
        output = formatter.format(result_with_violations)
        lines = output.strip().split("\n")

        assert len(lines) == 3

    def test_format_inline_no_line(self, info_violation):
        """Violation with no file_path and no line: location is 'inline' without ':N' suffix."""
        result = ValidationResult(files_checked=1)
        result.violations = [info_violation]
        formatter = CompactFormatter()
        output = formatter.format(result)

        # The format template adds ": " after location, so output contains "inline: "
        # but the location itself has no line number appended (no "inline:5" pattern)
        assert "inline: Trailing whitespace" in output

    def test_is_output_formatter_subclass(self):
        assert issubclass(CompactFormatter, OutputFormatter)


@pytest.mark.unit
class TestSarifFormatter:
    """Tests for SarifFormatter."""

    def test_format_returns_valid_json(self, result_with_violations):
        formatter = SarifFormatter()
        output = formatter.format(result_with_violations)
        parsed = json.loads(output)

        assert isinstance(parsed, dict)

    def test_sarif_schema_structure(self, result_with_violations):
        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(result_with_violations))

        assert parsed["version"] == "2.1.0"
        assert "$schema" in parsed
        assert "runs" in parsed
        assert len(parsed["runs"]) == 1

        run = parsed["runs"][0]
        assert "tool" in run
        assert "results" in run
        assert run["tool"]["driver"]["name"] == "DBLift"

    def test_build_rules_dedup(self):
        """Duplicate rule_ids should only appear once in rules."""
        v1 = ValidationViolation(
            rule_id="BR001",
            severity=ViolationSeverity.ERROR,
            message="msg1",
            source=ViolationSource.BUSINESS_RULE,
        )
        v2 = ValidationViolation(
            rule_id="BR001",
            severity=ViolationSeverity.ERROR,
            message="msg2",
            source=ViolationSource.BUSINESS_RULE,
        )
        result = ValidationResult(files_checked=1)
        result.violations = [v1, v2]

        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(result))

        rules = parsed["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "BR001"

    def test_build_results_with_file_path(self, error_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [error_violation]
        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(result))

        sarif_result = parsed["runs"][0]["results"][0]
        assert sarif_result["ruleId"] == "BR001"
        assert sarif_result["level"] == "error"
        assert "locations" in sarif_result

        location = sarif_result["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == "migrations/V1__init.sql"
        assert location["region"]["startLine"] == 10
        assert location["region"]["startColumn"] == 5

    def test_build_results_without_file_path(self, info_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [info_violation]
        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(result))

        sarif_result = parsed["runs"][0]["results"][0]
        assert "locations" not in sarif_result

    def test_rule_uses_message_as_description(self, error_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [error_violation]
        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(result))

        rule = parsed["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["shortDescription"]["text"] == "SELECT * is not allowed"

    def test_rule_description_uses_message(self, warning_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [warning_violation]
        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(result))

        rule = parsed["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["shortDescription"]["text"] == "Missing index on foreign key"

    def test_empty_violations(self, empty_result):
        formatter = SarifFormatter()
        parsed = json.loads(formatter.format(empty_result))

        run = parsed["runs"][0]
        assert run["tool"]["driver"]["rules"] == []
        assert run["results"] == []

    def test_is_output_formatter_subclass(self):
        assert issubclass(SarifFormatter, OutputFormatter)


@pytest.mark.unit
class TestGitHubActionsFormatter:
    """Tests for GitHubActionsFormatter."""

    def test_format_no_violations(self, empty_result):
        formatter = GitHubActionsFormatter()
        output = formatter.format(empty_result)

        assert output.startswith("::notice::")
        assert "5 checked" in output
        assert "no findings" in output

    def test_format_error_violation(self, error_violation):
        result = ValidationResult(files_checked=1, success=False)
        result.violations = [error_violation]
        formatter = GitHubActionsFormatter()
        output = formatter.format(result)

        assert output.startswith("::error file=")
        assert "file=migrations/V1__init.sql" in output
        assert "line=10" in output
        assert "SELECT * is not allowed [BR001]" in output

    def test_format_warning_violation(self, warning_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [warning_violation]
        formatter = GitHubActionsFormatter()
        output = formatter.format(result)

        assert "::warning file=" in output

    def test_format_info_violation(self, info_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [info_violation]
        formatter = GitHubActionsFormatter()
        output = formatter.format(result)

        assert "::notice file=" in output
        assert "file=unknown" in output
        assert "line=1" in output

    def test_format_omits_suggestion_from_annotation(self, error_violation):
        result = ValidationResult(files_checked=1, success=False)
        result.violations = [error_violation]
        formatter = GitHubActionsFormatter()
        output = formatter.format(result)

        assert "Suggestion:" not in output

    def test_format_without_suggestion(self, warning_violation):
        result = ValidationResult(files_checked=1)
        result.violations = [warning_violation]
        formatter = GitHubActionsFormatter()
        output = formatter.format(result)

        assert "Suggestion:" not in output

    def test_format_multiple_violations(self, result_with_violations):
        formatter = GitHubActionsFormatter()
        output = formatter.format(result_with_violations)
        lines = output.strip().split("\n")

        assert len(lines) == 3
        assert lines[0].startswith("::error")
        assert lines[1].startswith("::warning")
        assert lines[2].startswith("::notice")

    def test_is_output_formatter_subclass(self):
        assert issubclass(GitHubActionsFormatter, OutputFormatter)


@pytest.mark.unit
class TestFormatterFactory:
    """Tests for FormatterFactory."""

    @pytest.mark.parametrize(
        "format_name, expected_class",
        [
            ("console", ConsoleFormatter),
            ("json", JSONFormatter),
            ("sarif", SarifFormatter),
            ("github-actions", GitHubActionsFormatter),
            ("gitlab", GitLabFormatter),
            ("compact", CompactFormatter),
        ],
    )
    def test_create_valid_formats(self, format_name, expected_class):
        formatter = FormatterFactory.create(format_name)
        assert isinstance(formatter, expected_class)

    def test_create_case_insensitive(self):
        formatter = FormatterFactory.create("JSON")
        assert isinstance(formatter, JSONFormatter)

    def test_create_unknown_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown format: xml"):
            FormatterFactory.create("xml")

    def test_create_unknown_format_lists_available(self):
        with pytest.raises(ValueError, match="Available formats:"):
            FormatterFactory.create("unknown")

    def test_create_returns_new_instance_each_call(self):
        f1 = FormatterFactory.create("console")
        f2 = FormatterFactory.create("console")
        assert f1 is not f2

    def test_create_passes_fail_on_to_formatter(self):
        formatter = FormatterFactory.create("json", fail_on="warning")

        assert isinstance(formatter, JSONFormatter)
        assert formatter.fail_on == "warning"
