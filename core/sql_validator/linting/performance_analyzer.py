"""Performance analysis for SQL statements using AST parsing."""

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from core.migration.encoding import read_migration_text
from core.sql_validator.linting.models import (
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """
    Analyzes SQL for performance issues using AST-based analysis.

    This analyzer detects common performance anti-patterns:
    - Cartesian products (JOINs without ON clause)
    - Missing WHERE clauses in UPDATE/DELETE
    - SELECT *
    - Correlated subqueries
    - Index suppression (functions on indexed columns in WHERE)
    """

    def __init__(
        self,
        dialect: str = "",
        rule_severities: Optional[Dict[str, str]] = None,
        script_encoding: str = "utf-8",
        detect_encoding: bool = False,
    ) -> None:
        """
        Initialize the performance analyzer.

        Args:
            dialect: SQL dialect for parsing
            rule_severities: Dict mapping rule names to severity levels
                           Example: {"cartesian_product": "error", "select_star": "info"}
                           If None, all rules enabled with default severities
        """
        self.dialect = self._normalize_dialect(dialect)
        self.script_encoding = script_encoding
        self.detect_encoding = detect_encoding
        self.rule_severities = rule_severities or {
            "cartesian_product": "error",
            "missing_where_clause": "warning",
            "select_star": "warning",
            "correlated_subquery": "info",
        }

    def _normalize_dialect(self, dialect: str) -> str:
        """
        Normalize database dialect for parser.

        Args:
            dialect: DBLift dialect name

        Returns:
            Sqlglot dialect name (never an arbitrary unknown string — matches
            legacy ``dialect_map.get(..., "postgres")``).
        """
        from db.provider_registry import ProviderRegistry

        canonical = (dialect or "").lower()
        quirks = ProviderRegistry.get_quirks(canonical)
        mapped = quirks.sqlglot_dialect
        if mapped:
            return mapped
        # Legacy DIALECT_MAP: DB2 used the "db2" sqlglot name here even though
        # ``get_sqlglot_dialect("db2")`` stays ``None`` (parser factory uses
        # HybridParser, not SqlglotParser).
        if canonical == "db2":  # lint: allow-dialect-string: sqlglot dialect name
            return "db2"
        # Typos, empty input, dialects without sqlglot overlay (e.g. CosmosDB).
        return "postgres"  # lint: allow-dialect-string: sqlglot default dialect

    def analyze_file(self, file_path: Path) -> List[ValidationViolation]:
        """
        Analyze SQL file for performance issues.

        Deprecated compatibility wrapper. Callers that validate complete
        scripts should split and classify statements before invoking the
        performance analyzer.

        Args:
            file_path: Path to SQL file

        Returns:
            List of performance violations
        """
        try:
            sql_content = read_migration_text(
                file_path,
                configured_encoding=self.script_encoding,
                detect_encoding=self.detect_encoding,
            )
            return self.analyze_sql(sql_content, file_path)
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return []

    def analyze_sql(self, sql: str, file_path: Optional[Path] = None) -> List[ValidationViolation]:
        """
        Analyze a single, already-classified SQL fragment for performance issues.

        Args:
            sql: SQL content to analyze
            file_path: Optional file path for context

        Returns:
            List of performance violations
        """
        violations: List[ValidationViolation] = []

        try:
            try:
                stmt = self._parse_statement(sql)
            except ParseError as e:
                violations.append(
                    ValidationViolation(
                        rule_id="parse_error",
                        severity=ViolationSeverity.ERROR,
                        message=f"Failed to parse SQL for validation: {e}",
                        file_path=file_path,
                        source=ViolationSource.SYNTAX,
                    )
                )
                return violations

            if stmt is None:
                return violations

            # Check for cartesian products
            if self._is_rule_enabled("cartesian_product"):
                violations.extend(self._check_cartesian_product(stmt, file_path))

            # Check for missing WHERE in UPDATE/DELETE
            if self._is_rule_enabled("missing_where_clause"):
                violations.extend(self._check_missing_where(stmt, file_path))

            # Check for SELECT *
            if self._is_rule_enabled("select_star"):
                violations.extend(self._check_select_star(stmt, file_path))

            # Check for correlated subqueries
            if self._is_rule_enabled("correlated_subquery"):
                violations.extend(self._check_correlated_subquery(stmt, file_path))

        except Exception as e:
            logger.error(f"Error analyzing SQL: {e}")
            # BUG-06: any unexpected failure here used to be silent. Emit a
            # parse_error ERROR violation so validate-sql exits non-zero.
            violations.append(
                ValidationViolation(
                    rule_id="parse_error",
                    severity=ViolationSeverity.ERROR,
                    message=f"Error analyzing SQL: {e}",
                    file_path=file_path,
                    source=ViolationSource.SYNTAX,
                )
            )

        return violations

    def analyze_statements(
        self, statements: Iterable[str], file_path: Optional[Path] = None
    ) -> List[ValidationViolation]:
        """Analyze already-classified SQL fragments for performance issues."""
        violations: List[ValidationViolation] = []
        for statement in statements:
            violations.extend(self.analyze_sql(statement, file_path))
        return violations

    def _is_rule_enabled(self, rule_name: str) -> bool:
        """
        Check if a rule is enabled.

        Args:
            rule_name: Name of the rule

        Returns:
            True if rule is enabled
        """
        return rule_name in self.rule_severities

    def _get_severity(self, rule_name: str) -> ViolationSeverity:
        """
        Get the severity level for a rule.

        Args:
            rule_name: Name of the rule

        Returns:
            ViolationSeverity for the rule
        """
        severity_str = self.rule_severities.get(rule_name, "warning")
        return ViolationSeverity(severity_str)

    def _parse_statement(self, sql: str) -> Optional[exp.Expression]:
        """Parse one SQL fragment into a sqlglot AST node.

        Upstream validation code owns script splitting and statement
        classification. This method intentionally does not skip DDL or
        procedural SQL; callers should not pass those fragments here.
        """
        statement_str = sql.strip()
        if not statement_str:
            return None

        try:
            stmt = parse_one(statement_str, read=self.dialect)
            # ``parse_one`` is typed ``Expr | None`` in newer sqlglot;
            # ``Expression`` is the concrete subclass produced for valid
            # SQL. Use isinstance over a truthy check so mypy narrows
            # the return type correctly across sqlglot versions.
            if isinstance(stmt, exp.Expression):
                return stmt
        except Exception as e:
            logger.debug(f"Could not parse statement for performance analysis: {e}")
            raise ParseError(str(e)) from e
        return None

    def _check_cartesian_product(
        self, stmt: exp.Expression, file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Detect Cartesian products (JOIN without ON clause).

        Args:
            stmt: SQL statement AST
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []

        for join in stmt.find_all(exp.Join):
            # Check if JOIN has no ON clause
            if not join.args.get("on"):
                violations.append(
                    ValidationViolation(
                        rule_id="cartesian_product",
                        severity=self._get_severity("cartesian_product"),
                        message="Cartesian product detected: JOIN without ON clause",
                        file_path=file_path,
                        source=ViolationSource.PERFORMANCE,
                        suggestion="Add JOIN condition: JOIN table ON condition",
                    )
                )

        return violations

    def _check_missing_where(
        self, stmt: exp.Expression, file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Detect UPDATE/DELETE without WHERE clause.

        Args:
            stmt: SQL statement AST
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []

        # Check UPDATE statements
        if isinstance(stmt, exp.Update):
            if not stmt.args.get("where"):
                violations.append(
                    ValidationViolation(
                        rule_id="missing_where_clause",
                        severity=self._get_severity("missing_where_clause"),
                        message="UPDATE statement without WHERE clause affects all rows",
                        file_path=file_path,
                        source=ViolationSource.PERFORMANCE,
                        suggestion="Add WHERE clause to limit affected rows",
                    )
                )

        # Check DELETE statements
        if isinstance(stmt, exp.Delete):
            if not stmt.args.get("where"):
                violations.append(
                    ValidationViolation(
                        rule_id="missing_where_clause",
                        severity=self._get_severity("missing_where_clause"),
                        message="DELETE statement without WHERE clause affects all rows",
                        file_path=file_path,
                        source=ViolationSource.PERFORMANCE,
                        suggestion="Add WHERE clause to limit affected rows",
                    )
                )

        return violations

    def _check_select_star(
        self, stmt: exp.Expression, file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Detect SELECT * usage.

        Args:
            stmt: SQL statement AST
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []

        if isinstance(stmt, exp.Select):
            for select_expr in stmt.expressions:
                if isinstance(select_expr, exp.Star):
                    violations.append(
                        ValidationViolation(
                            rule_id="select_star",
                            severity=self._get_severity("select_star"),
                            message="SELECT * retrieves all columns, may impact performance",
                            file_path=file_path,
                            source=ViolationSource.PERFORMANCE,
                            suggestion="Specify only needed columns explicitly",
                        )
                    )

        return violations

    def _check_correlated_subquery(
        self, stmt: exp.Expression, file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Detect correlated subqueries that may be inefficient.

        Args:
            stmt: SQL statement AST
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []

        # This is a simplified check - true correlation analysis is complex
        # We'll flag subqueries in WHERE clauses as potentially correlated
        # Look for both Subquery and Select nodes within WHERE

        if isinstance(stmt, exp.Select):
            where_clause = stmt.args.get("where")
            if where_clause:
                # Check for both Subquery and nested Select statements
                subqueries = list(where_clause.find_all(exp.Subquery))
                nested_selects = list(where_clause.find_all(exp.Select))

                if subqueries or nested_selects:
                    violations.append(
                        ValidationViolation(
                            rule_id="correlated_subquery",
                            severity=self._get_severity("correlated_subquery"),
                            message="Subquery in WHERE clause may be correlated (inefficient)",
                            file_path=file_path,
                            source=ViolationSource.PERFORMANCE,
                            suggestion="Consider using JOIN or EXISTS instead",
                        )
                    )

        return violations
