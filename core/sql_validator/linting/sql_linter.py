"""SQL linter combining business rules and performance analysis."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from core.migration.encoding import read_migration_text

if TYPE_CHECKING:
    from sqlfluff.core import FluffConfig, Linter
    from sqlfluff.core.linter import LintedFile
else:
    # Runtime stubs for when sqlfluff is not installed
    FluffConfig = Any  # type: ignore
    Linter = Any  # type: ignore
    LintedFile = Any  # type: ignore

from core.sql_validator.linting.models import (
    ValidationResult,
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)
from core.sql_validator.linting.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class SqlLinter:
    """
    Main SQL linting class that coordinates business rule validation.

    This class uses an underlying linting engine to validate SQL files
    against custom declarative rules without exposing implementation details.
    """

    config: Optional[Any]  # FluffConfig when sqlfluff available
    linter: Optional[Any]  # Linter when sqlfluff available

    def __init__(
        self,
        dialect: str,
        rules_config: Optional[Dict[str, Any]] = None,
        custom_rules_path: Optional[Path] = None,
        custom_rules_data: Optional[Dict[str, Any]] = None,
        script_encoding: str = "utf-8",
        detect_encoding: bool = False,
    ) -> None:
        """
        Initialize the SQL linter.

        Args:
            dialect: Database dialect (oracle, postgres, mysql, tsql, db2)
            rules_config: Configuration dictionary for linting
            custom_rules_path: Path to custom YAML rules file
        """
        self.dialect = self._normalize_dialect(dialect)
        self.rules_config = rules_config or {}
        self.custom_rules_path = custom_rules_path
        self.custom_rules_data = custom_rules_data
        self.script_encoding = script_encoding
        self.detect_encoding = detect_encoding

        # Initialize rule engine for custom declarative rules
        # Map normalized dialect back to SQL Model dialect names
        sql_model_dialect = self._get_sql_model_dialect(dialect)
        self.rule_engine = RuleEngine(dialect=sql_model_dialect)
        if custom_rules_path and custom_rules_path.exists():
            self.rule_engine.load_rules_from_file(custom_rules_path)
        if custom_rules_data:
            self.rule_engine.load_rules_from_dict(custom_rules_data)

        # Initialize underlying linting engine
        self._init_linter()

    def _normalize_dialect(self, dialect: str) -> str:
        """
        Normalize database dialect to linter-compatible name.

        Args:
            dialect: DBLift dialect name

        Returns:
            Normalized dialect name
        """
        # Story 26-9: sqlglot dialect mapping owned by plugin Quirks
        # via the central ``get_sqlglot_dialect`` helper.
        from core.sql_model.dialect import get_sqlglot_dialect

        normalized = get_sqlglot_dialect(dialect) or dialect.lower()
        logger.debug(f"Normalized dialect '{dialect}' to '{normalized}'")
        return normalized

    def _get_sql_model_dialect(self, dialect: str) -> str:
        """
        Get SQL Model dialect name from DBLift dialect.

        Args:
            dialect: DBLift dialect name

        Returns:
            SQL Model dialect name
        """
        # Story 26-9: alias normalisation comes from the plugin
        # registry (PluginInfo.dialects).
        #
        # ``"tsql"`` is the sqlglot/sqlfluff name for SQL Server; the framework
        # canonical name is ``"sqlserver"``. Plugins register ``"tsql"`` when
        # discovery runs — if lookup misses anyway, map explicitly.
        from db.provider_registry import ProviderRegistry

        d = (dialect or "").lower()
        sql_model_dialect = ProviderRegistry.canonical_dialect_name(d)
        if sql_model_dialect is None:
            # lint: allow-dialect-string: sqlglot/sqlfluff ↔ framework dialect
            sql_model_dialect = "sqlserver" if d == "tsql" else d
        logger.debug(f"Mapped dialect '{dialect}' to SQL Model dialect '{sql_model_dialect}'")
        return sql_model_dialect

    def _init_linter(self) -> None:
        """Initialize the underlying linting engine."""
        # Build configuration
        # Note: dialect must be at root level, not under "core"
        config_dict: Dict[str, Any] = {
            "dialect": self.dialect,
            "core": {
                "exclude_rules": self.rules_config.get("exclude_rules", []),
                "rules": self._build_rule_config(),
            },
            "layout": {
                "type": {
                    "alias_expression": {
                        "spacing_before": "touch",
                        "spacing_after": "touch",
                    }
                }
            },
        }

        # Create config and linter (lazy import to avoid circular dependency)
        try:
            from sqlfluff.core import FluffConfig, Linter

            self.config = FluffConfig(overrides=config_dict)
            self.linter = Linter(config=self.config)
            logger.debug(f"Initialized linter with dialect: {self.dialect}")
        except ImportError as e:
            logger.warning(f"sqlfluff not available: {e}. SQL linting will be limited.")
            self.config = None
            self.linter = None

    def _build_rule_config(self) -> Dict[str, Any]:
        """
        Build rule configuration from custom rules.

        Returns:
            Rule configuration dictionary
        """
        # Get rules from rule engine
        rules: Dict[str, Any] = self.rules_config.get("rules", {})
        return rules

    def lint_file(self, file_path: Path) -> ValidationResult:
        """
        Lint a single SQL file.

        Args:
            file_path: Path to SQL file to lint

        Returns:
            ValidationResult containing any violations found
        """
        result = ValidationResult(files_checked=1)

        try:
            # Read file content
            sql_content = read_migration_text(
                file_path,
                configured_encoding=self.script_encoding,
                detect_encoding=self.detect_encoding,
            )

            # Lint the content (skip if sqlfluff not available)
            if self.linter is not None:
                linted_result = self.linter.lint_string(sql_content, fname=str(file_path))
                # Convert violations
                self._process_linting_result(linted_result, file_path, result)

            # Apply custom declarative rules
            custom_violations = self.rule_engine.check_sql(sql_content, file_path)
            for violation in custom_violations:
                result.add_violation(violation)

        except Exception as e:
            logger.error(f"Error linting file {file_path}: {e}")
            result.add_violation(
                ValidationViolation(
                    rule_id="linting_error",
                    severity=ViolationSeverity.ERROR,
                    message=f"Failed to lint file: {str(e)}",
                    file_path=file_path,
                    source=ViolationSource.SYNTAX,
                )
            )

        return result

    def lint_string(self, sql: str, file_path: Optional[Path] = None) -> ValidationResult:
        """
        Lint SQL string content.

        Args:
            sql: SQL content to lint
            file_path: Optional file path for context

        Returns:
            ValidationResult containing any violations found
        """
        result = ValidationResult(files_checked=1)

        try:
            # Lint the content (skip if sqlfluff not available)
            if self.linter is not None:
                linted_result = self.linter.lint_string(
                    sql, fname=str(file_path) if file_path else "inline"
                )

                # Convert violations
                self._process_linting_result(linted_result, file_path, result)

            # Apply custom declarative rules
            custom_violations = self.rule_engine.check_sql(sql, file_path)
            for violation in custom_violations:
                result.add_violation(violation)

        except Exception as e:
            logger.error(f"Error linting SQL string: {e}")
            result.add_violation(
                ValidationViolation(
                    rule_id="linting_error",
                    severity=ViolationSeverity.ERROR,
                    message=f"Failed to lint SQL: {str(e)}",
                    file_path=file_path,
                    source=ViolationSource.SYNTAX,
                )
            )

        return result

    def _process_linting_result(
        self, linted_result: Any, file_path: Optional[Path], result: ValidationResult
    ) -> None:
        """
        Process linting result and add violations.

        Args:
            linted_result: Result from linting engine
            file_path: File that was linted
            result: ValidationResult to add violations to
        """
        for violation in linted_result.violations:
            # Map severity
            severity = self._map_severity(violation.rule_code())

            # Create violation
            v = ValidationViolation(
                rule_id=violation.rule_code(),
                severity=severity,
                message=violation.desc(),
                file_path=file_path,
                line=violation.line_no,
                column=violation.line_pos,
                source=ViolationSource.SYNTAX,
                code_snippet=violation.context if hasattr(violation, "context") else None,
            )
            result.add_violation(v)

    def _map_severity(self, rule_code: str) -> ViolationSeverity:
        """
        Map rule code to severity level.

        Args:
            rule_code: Rule identifier

        Returns:
            Severity level for the rule
        """
        # Check if user configured severity
        rules_severity = self.rules_config.get("severity", {})
        if rule_code in rules_severity:
            severity_str = rules_severity[rule_code]
            return ViolationSeverity(severity_str)

        # Default: syntax errors are errors, everything else is warning
        if rule_code.startswith("PRS"):  # Parse errors
            return ViolationSeverity.ERROR
        return ViolationSeverity.WARNING

    def lint_directory(self, directory: Path, pattern: str = "*.sql") -> ValidationResult:
        """
        Lint all SQL files in a directory.

        Args:
            directory: Directory to search for SQL files
            pattern: File pattern to match (default: *.sql)

        Returns:
            Combined ValidationResult for all files
        """
        result = ValidationResult()

        sql_files = list(directory.rglob(pattern))
        result.files_checked = len(sql_files)

        for sql_file in sql_files:
            file_result = self.lint_file(sql_file)
            result.merge(file_result)

        return result
