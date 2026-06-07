"""SQL validation coordinator combining business rules and performance analysis."""

import logging
import re
from pathlib import Path
from typing import List, Optional

from config.validation_config import ValidationConfig
from core.migration.encoding import read_migration_text
from core.migration.sql.sql_analyzer import SqlAnalyzer
from core.sql_validator.linting.models import ValidationResult
from core.sql_validator.linting.performance_analyzer import PerformanceAnalyzer
from core.sql_validator.linting.sql_linter import SqlLinter
from core.sql_validator.rule_packs.resolver import resolve_validation_rules
from core.validation.failure_policy import (
    is_always_fail_source,
    normalize_fail_on,
    severity_meets_threshold,
)

logger = logging.getLogger(__name__)


class SqlValidator:
    """
    Coordinates SQL validation including business rules and performance analysis.

    This class combines:
    1. Business rule validation (from YAML rules)
    2. Performance analysis (AST-based)

    Output is unified and doesn't expose underlying tool names.
    """

    def __init__(
        self,
        dialect: str,
        validation_config: Optional[ValidationConfig] = None,
        script_encoding: str = "utf-8",
        detect_encoding: bool = False,
    ) -> None:
        """
        Initialize the SQL validator.

        Args:
            dialect: Database dialect (oracle, postgres, mysql, tsql, db2)
            validation_config: Validation configuration
        """
        self.dialect = dialect
        self.config = validation_config or ValidationConfig()
        self.script_encoding = script_encoding
        self.detect_encoding = detect_encoding
        self.sql_analyzer = SqlAnalyzer(dialect=dialect)

        # Initialize business rule linter (only if rules file specified)
        self.linter: Optional[SqlLinter] = None
        if self.config.enabled:
            rules_path = self.config.get_rules_path()
            rules_data = resolve_validation_rules(self.config)
            if rules_data or (rules_path and rules_path.exists()):
                self.linter = SqlLinter(
                    dialect=dialect,
                    rules_config={},
                    custom_rules_path=rules_path,
                    custom_rules_data=rules_data,
                    script_encoding=script_encoding,
                    detect_encoding=detect_encoding,
                )

        # Initialize performance analyzer
        self.performance_analyzer: Optional[PerformanceAnalyzer] = None
        if self.config.enabled and self.config.performance_enabled:
            self.performance_analyzer = PerformanceAnalyzer(
                dialect=dialect,
                rule_severities=self.config.performance_rules,
                script_encoding=script_encoding,
                detect_encoding=detect_encoding,
            )

    def validate_file(self, file_path: Path) -> ValidationResult:
        """
        Validate a single SQL file.

        Args:
            file_path: Path to SQL file

        Returns:
            ValidationResult containing all violations
        """
        result = ValidationResult(files_checked=1)

        if not self.config.enabled:
            return result

        # Check exclude patterns
        if self._should_exclude(file_path):
            logger.debug(f"Skipping excluded file: {file_path}")
            return result

        try:
            sql_content = read_migration_text(
                file_path,
                configured_encoding=self.script_encoding,
                detect_encoding=self.detect_encoding,
            )

            # Run business rule validation
            if self.linter:
                lint_result = self.linter.lint_file(file_path)
                result.merge(lint_result)

            # Run performance analysis
            if self.performance_analyzer:
                performance_sql = self._extract_performance_sql(sql_content)
                perf_violations = self.performance_analyzer.analyze_statements(
                    performance_sql, file_path
                )
                for violation in perf_violations:
                    result.add_violation(violation)

            # Apply severity threshold filter
            result = self._filter_by_severity(result)

        except Exception as e:
            logger.error(f"Error validating file {file_path}: {e}")

        return result

    def _extract_performance_sql(self, sql_content: str) -> List[str]:
        """Return statements whose top-level form is relevant to performance rules."""
        statements = self.sql_analyzer.split_statements(sql_content)
        return [
            statement
            for statement in statements
            if self._is_performance_relevant_statement(statement)
        ]

    def _is_performance_relevant_statement(self, statement: str) -> bool:
        """Only pass top-level query/DML forms current performance rules inspect."""
        first_keyword = self._first_sql_keyword(statement)
        if first_keyword not in {"SELECT", "UPDATE", "DELETE"}:
            return False

        statement_type = self.sql_analyzer.get_statement_type(statement)
        return statement_type in {"QUERY", "DML"}

    def _first_sql_keyword(self, statement: str) -> str:
        """Find the first SQL keyword after leading comments and whitespace."""
        sql = statement.lstrip("\ufeff").strip()
        while sql:
            if sql.startswith("--"):
                _, sep, rest = sql.partition("\n")
                sql = rest if sep else ""
                sql = sql.strip()
                continue
            if sql.startswith("/*"):
                end = sql.find("*/")
                if end == -1:
                    return ""
                sql = sql[end + 2 :].strip()
                continue
            break

        match = re.match(r"[A-Za-z_]+", sql)
        return match.group(0).upper() if match else ""

    def validate_files(self, file_paths: List[Path]) -> ValidationResult:
        """
        Validate multiple SQL files.

        Args:
            file_paths: List of SQL file paths

        Returns:
            Combined ValidationResult
        """
        combined_result = ValidationResult()

        for file_path in file_paths:
            file_result = self.validate_file(file_path)
            combined_result.merge(file_result)

        return combined_result

    def validate_directory(
        self, directory: Path, pattern: str = "*.sql", recursive: bool = True
    ) -> ValidationResult:
        """
        Validate all SQL files in a directory.

        Args:
            directory: Directory to search
            pattern: File pattern to match
            recursive: Whether to search recursively

        Returns:
            Combined ValidationResult
        """
        if recursive:
            sql_files = list(directory.rglob(pattern))
        else:
            sql_files = list(directory.glob(pattern))

        # Filter excluded files
        sql_files = [f for f in sql_files if not self._should_exclude(f)]

        return self.validate_files(sql_files)

    def _should_exclude(self, file_path: Path) -> bool:
        """
        Check if file should be excluded based on patterns.

        Args:
            file_path: File to check

        Returns:
            True if file should be excluded
        """
        file_str = str(file_path)
        for pattern in self.config.exclude_patterns:
            # Simple wildcard matching
            if pattern.replace("*", "") in file_str:
                return True
        return False

    def _filter_by_severity(self, result: ValidationResult) -> ValidationResult:
        """
        Filter violations by severity threshold.

        Args:
            result: ValidationResult to filter

        Returns:
            Filtered ValidationResult
        """
        # Map severity threshold to numeric value
        severity_levels = {"error": 3, "warning": 2, "info": 1}
        threshold = severity_levels.get(self.config.severity_threshold, 2)

        filtered_violations = []
        for violation in result.violations:
            violation_level = severity_levels.get(violation.severity.value, 1)
            if violation_level >= threshold:
                filtered_violations.append(violation)

        result.violations = filtered_violations
        return result

    def should_fail(self, result: ValidationResult, fail_on: Optional[str] = None) -> bool:
        """
        Determine if validation should fail based on configuration.

        Args:
            result: ValidationResult to check

        Returns:
            True if should fail
        """
        threshold = normalize_fail_on(fail_on or self.config.fail_on)
        if any(is_always_fail_source(violation.source) for violation in result.violations):
            return True
        return any(
            severity_meets_threshold(violation.severity, threshold)
            for violation in result.violations
        )
