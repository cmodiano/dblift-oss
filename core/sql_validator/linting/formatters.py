"""Output formatters for validation results."""

from abc import ABC, abstractmethod
from typing import Dict, Type

from core.sql_validator.linting.models import ValidationResult


class OutputFormatter(ABC):
    """Base class for output formatters."""

    def __init__(self, fail_on: str = "error") -> None:
        """Initialize formatter with the finding threshold used by shared formats."""
        self.fail_on = fail_on

    @abstractmethod
    def format(self, result: ValidationResult) -> str:
        """Format validation result."""


class ConsoleFormatter(OutputFormatter):
    """Format validation results for console output."""

    def format(self, result: ValidationResult) -> str:
        """
        Format validation result for console.

        Args:
            result: ValidationResult to format

        Returns:
            Formatted string for console
        """
        return _format_shared(result, "console", self.fail_on)


class JSONFormatter(OutputFormatter):
    """Format validation results as JSON."""

    def format(self, result: ValidationResult) -> str:
        """
        Format validation result as JSON.

        Args:
            result: ValidationResult to format

        Returns:
            JSON string
        """
        return _format_shared(result, "json", self.fail_on)


class CompactFormatter(OutputFormatter):
    """Format validation results in compact one-line-per-violation format."""

    def format(self, result: ValidationResult) -> str:
        """
        Format validation result in compact format.

        Args:
            result: ValidationResult to format

        Returns:
            Compact formatted string
        """
        return _format_shared(result, "compact", self.fail_on)


class SarifFormatter(OutputFormatter):
    """Format validation results as SARIF (Static Analysis Results Interchange Format)."""

    def format(self, result: ValidationResult) -> str:
        """
        Format validation result as SARIF JSON.

        Args:
            result: ValidationResult to format

        Returns:
            SARIF JSON string
        """
        return _format_shared(result, "sarif", self.fail_on)


class GitHubActionsFormatter(OutputFormatter):
    """Format validation results for GitHub Actions annotations."""

    def format(self, result: ValidationResult) -> str:
        """
        Format validation result for GitHub Actions.

        Args:
            result: ValidationResult to format

        Returns:
            GitHub Actions annotation format
        """
        return _format_shared(result, "github-actions", self.fail_on)


class GitLabFormatter(OutputFormatter):
    """Format validation results for GitLab Code Quality reports."""

    def format(self, result: ValidationResult) -> str:
        """Format validation result as GitLab Code Quality JSON."""
        return _format_shared(result, "gitlab", self.fail_on)


def _format_shared(result: ValidationResult, output_format: str, fail_on: str = "error") -> str:
    """Delegate legacy formatter classes to the shared findings formatter."""
    from core.ci.formatters import format_finding_report
    from core.ci.sql_validation import validation_result_to_finding_report

    result_fail_on = str(getattr(result, "fail_on", fail_on) or fail_on)
    report = validation_result_to_finding_report(result, result_fail_on)
    return format_finding_report(report, output_format)


class FormatterFactory:
    """Factory for creating output formatters."""

    @staticmethod
    def create(format_name: str, fail_on: str = "error") -> OutputFormatter:
        """
        Create an output formatter.

        Args:
            format_name: Name of the format (console, json, sarif, github-actions, compact)

        Returns:
            OutputFormatter instance

        Raises:
            ValueError: If format name is unknown
        """
        formatters: Dict[str, Type[OutputFormatter]] = {
            "console": ConsoleFormatter,
            "json": JSONFormatter,
            "sarif": SarifFormatter,
            "github-actions": GitHubActionsFormatter,
            "gitlab": GitLabFormatter,
            "compact": CompactFormatter,
        }

        formatter_class = formatters.get(format_name.lower())
        if not formatter_class:
            raise ValueError(
                f"Unknown format: {format_name}. "
                f"Available formats: {', '.join(formatters.keys())}"
            )

        return formatter_class(fail_on=fail_on)
