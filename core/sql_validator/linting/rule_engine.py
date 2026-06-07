"""Rule engine for declarative YAML-based SQL validation rules."""

import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Tuple, cast

import yaml  # type: ignore[import-untyped]

from core.migration.sql.sql_analyzer import SqlAnalyzer
from core.sql_model.base import ParseResult
from core.sql_model.table import Table
from core.sql_validator.linting.models import (
    ValidationViolation,
    ViolationSeverity,
    ViolationSource,
)

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Engine for loading and executing declarative YAML rules.

    Currently supports:
    - naming: Validate identifier naming conventions (regex-based on raw SQL)
    - pattern: Detect SQL patterns (e.g., SELECT *, anti-patterns)

    TODO: Future enhancements with SQLModel integration:
    - presence: Check for required elements (e.g., primary keys, audit columns)
    - relational: Validate relationships (e.g., FK must have index)
    These will require integration with parsed SQLModel objects from HybridParser.
    """

    def __init__(
        self,
        dialect: str = "",
    ) -> None:
        """Initialize the rule engine.

        Args:
            dialect: SQL dialect for parsing (postgresql, mysql, oracle, sqlserver, db2)
        """
        self.rules: List[Dict[str, Any]] = []
        self.naming_rules: List[Dict[str, Any]] = []
        self.pattern_rules: List[Dict[str, Any]] = []
        self.presence_rules: List[Dict[str, Any]] = []
        self.relational_rules: List[Dict[str, Any]] = []

        # Initialize SqlAnalyzer for DDL parsing
        self.dialect = dialect
        self.sql_analyzer = SqlAnalyzer(dialect)

    def load_rules_from_file(self, rules_path: Path) -> None:
        """
        Load rules from YAML file.

        Args:
            rules_path: Path to YAML rules file
        """
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_data = yaml.safe_load(f)

            if not rules_data or "rules" not in rules_data:
                logger.warning(f"No rules found in {rules_path}")
                return

            self.rules = rules_data["rules"]
            self._categorize_rules()

            logger.info(f"Loaded {len(self.rules)} rules from {rules_path}")

        except Exception as e:
            logger.error(f"Failed to load rules from {rules_path}: {e}")
            raise

    def load_rules_from_dict(self, rules_data: Dict[str, Any]) -> None:
        """
        Load rules from dictionary.

        Args:
            rules_data: Dictionary containing rules
        """
        if "rules" in rules_data:
            self.rules = rules_data["rules"]
            self._categorize_rules()
            logger.info(f"Loaded {len(self.rules)} rules from dictionary")

    def _categorize_rules(self) -> None:
        """Categorize rules by type for efficient processing."""
        self.naming_rules = []
        self.pattern_rules = []
        self.presence_rules = []
        self.relational_rules = []

        for rule in self.rules:
            rule_type = rule.get("type")
            if rule_type == "naming":
                self.naming_rules.append(rule)
            elif rule_type == "pattern":
                self.pattern_rules.append(rule)
            elif rule_type == "presence":
                self.presence_rules.append(rule)
            elif rule_type == "relational":
                self.relational_rules.append(rule)
            else:
                logger.warning(f"Unknown rule type: {rule_type} for rule: {rule.get('name')}")

    def check_sql(self, sql: str, file_path: Optional[Path] = None) -> List[ValidationViolation]:
        """
        Check SQL content against all loaded rules.

        Args:
            sql: SQL content to check
            file_path: Optional file path for context

        Returns:
            List of validation violations
        """
        violations: List[ValidationViolation] = []

        try:
            # Detect context (e.g., if SQL is in a view)
            self._detect_context(sql)

            # Apply naming rules (regex-based on raw SQL)
            for rule in self.naming_rules:
                violations.extend(self._check_naming_rule(sql, rule, file_path))

            # Apply pattern rules (regex-based on raw SQL)
            for rule in self.pattern_rules:
                violations.extend(self._check_pattern_rule(sql, rule, file_path))

            # Apply presence rules (using SQL Model objects)
            if self.presence_rules:
                tables = self.sql_analyzer.get_tables(sql)
                for rule in self.presence_rules:
                    violations.extend(self._check_presence_rule(tables, rule, file_path))

            # Apply relational rules (using SQL Model objects)
            if self.relational_rules:
                parse_result = self.sql_analyzer.parse_sql(sql)
                for rule in self.relational_rules:
                    violations.extend(self._check_relational_rule(parse_result, rule, file_path))

        except Exception as e:
            logger.error(f"Error checking SQL rules: {e}")

        return violations

    def _detect_context(self, sql: str) -> Dict[str, Any]:
        """
        Detect context from SQL content (e.g., if it's in a view, temp table, etc.).

        Args:
            sql: SQL content

        Returns:
            Dictionary with context information
        """
        context: Dict[str, Any] = {}

        # Check if SQL is in a view
        if re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW", sql, re.IGNORECASE):
            context["in_view"] = True

        # Check if SQL is in a temporary table
        if re.search(r"CREATE\s+(?:GLOBAL\s+)?TEMPORARY\s+TABLE", sql, re.IGNORECASE):
            context["in_temp_table"] = True

        return context

    def _matching_exception(
        self,
        rule: Dict[str, Any],
        sql: str,
        table_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the first exception matching this SQL context."""
        exceptions = rule.get("exceptions", [])
        if not exceptions:
            return None

        context = context or {}
        for raw_exception in exceptions:
            if not isinstance(raw_exception, dict):
                continue
            exception = cast(Dict[str, Any], raw_exception)
            if "table_matches" in exception and table_name:
                table_pattern = re.compile(exception["table_matches"], re.IGNORECASE)
                if table_pattern.match(table_name):
                    return exception
            if "when" in exception:
                when_pattern = exception["when"]
                if re.search(re.escape(when_pattern), sql, re.IGNORECASE):
                    return exception
            if exception.get("in_views"):
                if context.get("in_view", False):
                    return exception
                if re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW", sql, re.IGNORECASE):
                    return exception
            if exception.get("in_temp_tables"):
                if context.get("in_temp_table", False):
                    return exception
                if re.search(r"CREATE\s+(?:GLOBAL\s+)?TEMPORARY\s+TABLE", sql, re.IGNORECASE):
                    return exception
        return None

    def _exception_error(
        self,
        rule: Dict[str, Any],
        exception: Dict[str, Any],
        file_path: Optional[Path],
    ) -> Optional[ValidationViolation]:
        """Return a violation when a governed exception is incomplete or expired."""
        if exception.get("policy_exempt") is True:
            return None

        required = list((rule.get("override_policy") or {}).get("requires", []))
        max_days = (rule.get("override_policy") or {}).get("max_days")
        if isinstance(max_days, int) and "expires_at" not in required:
            required.append("expires_at")
        missing = [field for field in required if not exception.get(field)]
        expires_at = exception.get("expires_at")
        if expires_at:
            try:
                expiration_date = date.fromisoformat(str(expires_at))
                today = date.today()
                if expiration_date < today:
                    missing.append("expires_at:not_expired")
                if isinstance(max_days, int) and expiration_date > today + timedelta(days=max_days):
                    missing.append(f"expires_at:within_{max_days}_days")
            except ValueError:
                missing.append("expires_at:iso_date")
        if not missing:
            return None
        return ValidationViolation(
            rule_id=f"{rule.get('name', 'rule')}.exception",
            severity=ViolationSeverity.ERROR,
            message=(
                "Policy exception for "
                f"{rule.get('name', 'rule')} is missing required evidence: " + ", ".join(missing)
            ),
            file_path=file_path,
            source=ViolationSource.BUSINESS_RULE,
            exception=self._serializable_exception(exception),
            **self._violation_metadata(rule),
        )

    def _serializable_exception(self, exception: Dict[str, Any]) -> Dict[str, Any]:
        """Return exception evidence safe for JSON and HTML report rendering."""
        return {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in exception.items()
        }

    def _exception_status(
        self,
        rule: Dict[str, Any],
        sql: str,
        file_path: Optional[Path],
        table_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[ValidationViolation]]:
        """Return whether an exception matched and any governance error it carries."""
        exception = self._matching_exception(rule, sql, table_name=table_name, context=context)
        if not exception:
            return False, None
        return True, self._exception_error(rule, exception, file_path)

    def _violation_metadata(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Return enterprise metadata copied from a rule into its violations."""
        control_mapping = rule.get("control_mapping") or []
        if isinstance(control_mapping, str):
            control_mapping = [control_mapping]
        return {
            "rationale": rule.get("rationale"),
            "remediation": rule.get("remediation"),
            "control_mapping": list(control_mapping),
            "override_policy": dict(rule.get("override_policy") or {}),
        }

    def _check_naming_rule(
        self, sql: str, rule: Dict[str, Any], file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Check naming convention rules using regex on raw SQL.

        Args:
            sql: Raw SQL content
            rule: Naming rule definition
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []
        target = rule.get("target")
        pattern_str = rule.get("pattern")

        if not pattern_str:
            return violations

        # Don't use IGNORECASE for naming rules - naming conventions are case-sensitive
        pattern: Pattern[str] = re.compile(pattern_str)

        # Extract identifiers based on target type using regex
        # This is a simplified approach - full DDL parsing is done by HybridParser

        if target == "table":
            # Match CREATE TABLE, ALTER TABLE statements
            table_pattern = re.compile(
                r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
                re.IGNORECASE,
            )
            for match in table_pattern.finditer(sql):
                table_name = match.group(1)
                if not pattern.match(table_name):
                    exception_matched, exception_error = self._exception_status(
                        rule, sql, file_path, table_name=table_name
                    )
                    if exception_matched:
                        if exception_error:
                            violations.append(exception_error)
                    else:
                        violations.append(
                            ValidationViolation(
                                rule_id=rule["name"],
                                severity=ViolationSeverity(rule.get("severity", "warning")),
                                message=f"{rule['message']} (found: {table_name})",
                                file_path=file_path,
                                source=ViolationSource.BUSINESS_RULE,
                                **self._violation_metadata(rule),
                            )
                        )

        elif target == "column":
            # Match column definitions in CREATE TABLE
            # This is simplified - full parsing requires HybridParser
            col_pattern = re.compile(
                r"\b(\w+)\s+(?:VARCHAR|INTEGER|INT|DATE|TIMESTAMP|NUMBER|DECIMAL)", re.IGNORECASE
            )
            for match in col_pattern.finditer(sql):
                column_name = match.group(1)
                if not pattern.match(column_name):
                    violations.append(
                        ValidationViolation(
                            rule_id=rule["name"],
                            severity=ViolationSeverity(rule.get("severity", "warning")),
                            message=f"{rule['message']} (found: {column_name})",
                            file_path=file_path,
                            source=ViolationSource.BUSINESS_RULE,
                            **self._violation_metadata(rule),
                        )
                    )

        elif target == "index":
            # Match CREATE [UNIQUE] INDEX [CONCURRENTLY] [IF NOT EXISTS] <name>.
            # PostgreSQL's ``CONCURRENTLY`` modifier sits between ``INDEX`` and
            # the name; we skip it (and any combination with ``IF NOT EXISTS``)
            # so the capture group always lands on the real index identifier.
            index_pattern = re.compile(
                r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+"
                r"(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
                r"(?:CONCURRENTLY\s+)?(\w+)",
                re.IGNORECASE,
            )
            for match in index_pattern.finditer(sql):
                index_name = match.group(1)
                if not pattern.match(index_name):
                    violations.append(
                        ValidationViolation(
                            rule_id=rule["name"],
                            severity=ViolationSeverity(rule.get("severity", "warning")),
                            message=f"{rule['message']} (found: {index_name})",
                            file_path=file_path,
                            source=ViolationSource.BUSINESS_RULE,
                            **self._violation_metadata(rule),
                        )
                    )

        elif target == "constraint":
            # Match named ``CONSTRAINT <name>`` clauses (inside CREATE TABLE
            # bodies or ALTER TABLE ADD CONSTRAINT statements). Skip
            # ``DROP CONSTRAINT <name>`` — those reference an existing name
            # being removed and shouldn't be re-validated.
            constraint_pattern = re.compile(r"(?<!DROP\s)CONSTRAINT\s+(\w+)", re.IGNORECASE)
            for match in constraint_pattern.finditer(sql):
                constraint_name = match.group(1)
                if not pattern.match(constraint_name):
                    violations.append(
                        ValidationViolation(
                            rule_id=rule["name"],
                            severity=ViolationSeverity(rule.get("severity", "warning")),
                            message=f"{rule['message']} (found: {constraint_name})",
                            file_path=file_path,
                            source=ViolationSource.BUSINESS_RULE,
                            **self._violation_metadata(rule),
                        )
                    )

        return violations

    def _check_pattern_rule(
        self, sql: str, rule: Dict[str, Any], file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Check SQL pattern rules using regex on raw SQL.

        Args:
            sql: Raw SQL content
            rule: Pattern rule definition
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []

        # Detect context for exception checking
        context = self._detect_context(sql)

        # Check for prohibited patterns
        prohibit = rule.get("prohibit")
        if prohibit:
            # Simple case-insensitive check
            if re.search(re.escape(prohibit), sql, re.IGNORECASE):
                exception_matched, exception_error = self._exception_status(
                    rule, sql, file_path, context=context
                )
                if exception_matched:
                    if exception_error:
                        violations.append(exception_error)
                else:
                    violations.append(
                        ValidationViolation(
                            rule_id=rule["name"],
                            severity=ViolationSeverity(rule.get("severity", "warning")),
                            message=rule["message"],
                            file_path=file_path,
                            source=ViolationSource.BUSINESS_RULE,
                            suggestion=rule.get("suggestion", "Avoid this pattern"),
                            **self._violation_metadata(rule),
                        )
                    )

        # Check for regex patterns
        if "regex" in rule:
            pattern: Pattern[str] = re.compile(rule["regex"], re.IGNORECASE)
            if pattern.search(sql):
                exception_matched, exception_error = self._exception_status(
                    rule, sql, file_path, context=context
                )
                if exception_matched:
                    if exception_error:
                        violations.append(exception_error)
                else:
                    violations.append(
                        ValidationViolation(
                            rule_id=rule["name"],
                            severity=ViolationSeverity(rule.get("severity", "warning")),
                            message=rule["message"],
                            file_path=file_path,
                            source=ViolationSource.BUSINESS_RULE,
                            suggestion=rule.get("suggestion"),
                            **self._violation_metadata(rule),
                        )
                    )

        return violations

    def _check_presence_rule(
        self, tables: List[Table], rule: Dict[str, Any], file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Check presence rules using SQL Model objects.

        Presence rules check for required elements like columns, constraints, or comments.

        Args:
            tables: List of Table objects from SQL Model
            rule: Presence rule definition
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []
        target = rule.get("target")

        if target == "table":
            for table in tables:
                exception_matched, exception_error = self._exception_status(
                    rule, "", file_path, table_name=table.name
                )
                if exception_matched:
                    if exception_error:
                        violations.append(exception_error)
                    continue

                # Check for required columns
                must_have_columns = rule.get("must_have_columns", [])
                for required_col in must_have_columns:
                    if not table.get_column(required_col):
                        violations.append(
                            ValidationViolation(
                                rule_id=rule["name"],
                                severity=ViolationSeverity(rule.get("severity", "warning")),
                                message=f"{rule['message']} (table: {table.name}, missing: {required_col})",
                                file_path=file_path,
                                source=ViolationSource.BUSINESS_RULE,
                                **self._violation_metadata(rule),
                            )
                        )

                # Check for required primary key
                if rule.get("must_have_primary_key", False):
                    if not table.get_primary_key():
                        violations.append(
                            ValidationViolation(
                                rule_id=rule["name"],
                                severity=ViolationSeverity(rule.get("severity", "error")),
                                message=f"{rule['message']} (table: {table.name})",
                                file_path=file_path,
                                source=ViolationSource.BUSINESS_RULE,
                                **self._violation_metadata(rule),
                            )
                        )

                # Check for required comment
                if rule.get("must_have_comment", False):
                    if not hasattr(table, "comment") or not table.comment:
                        violations.append(
                            ValidationViolation(
                                rule_id=rule["name"],
                                severity=ViolationSeverity(rule.get("severity", "info")),
                                message=f"{rule['message']} (table: {table.name})",
                                file_path=file_path,
                                source=ViolationSource.BUSINESS_RULE,
                                **self._violation_metadata(rule),
                            )
                        )

        return violations

    def _check_relational_rule(
        self, parse_result: ParseResult, rule: Dict[str, Any], file_path: Optional[Path]
    ) -> List[ValidationViolation]:
        """
        Check relational rules using SQL Model objects.

        Relational rules validate relationships between database objects,
        such as foreign key/index relationships.

        Args:
            parse_result: ParseResult containing tables and indexes
            rule: Relational rule definition
            file_path: Optional file path

        Returns:
            List of violations
        """
        violations: List[ValidationViolation] = []
        target = rule.get("target")

        if target == "foreign_key" and parse_result.tables:
            # Get all indexes for lookup
            indexes_by_table: Dict[str, List[Any]] = {}
            if parse_result.indexes:
                for index in parse_result.indexes:
                    table_name = index.table_name.lower() if index.table_name else ""
                    if table_name not in indexes_by_table:
                        indexes_by_table[table_name] = []
                    indexes_by_table[table_name].append(index)

            for table in parse_result.tables:
                fk_constraints = table.get_foreign_keys()

                for fk in fk_constraints:
                    # Check if FK requires an index
                    if rule.get("requires_index", False):
                        # Look for index on the same columns
                        has_matching_index = False

                        # Check indexes for this table
                        table_indexes = indexes_by_table.get(table.name.lower(), [])
                        for index in table_indexes:
                            if self._columns_match(fk.column_names, index.columns):
                                has_matching_index = True
                                break

                        # Check if FK columns form a primary key (also acts as index)
                        pk = table.get_primary_key()
                        if pk and self._columns_match(fk.column_names, pk.column_names):
                            has_matching_index = True

                        if not has_matching_index:
                            violations.append(
                                ValidationViolation(
                                    rule_id=rule["name"],
                                    severity=ViolationSeverity(rule.get("severity", "warning")),
                                    message=f"{rule['message']} (table: {table.name}, FK on: {', '.join(fk.column_names)})",
                                    file_path=file_path,
                                    source=ViolationSource.BUSINESS_RULE,
                                    **self._violation_metadata(rule),
                                )
                            )

        return violations

    def _columns_match(self, cols1: List[str], cols2: List[str]) -> bool:
        """
        Check if two column lists match (case-insensitive, order matters for indexes).

        Args:
            cols1: First column list
            cols2: Second column list

        Returns:
            True if columns match, False otherwise
        """
        if len(cols1) != len(cols2):
            return False

        # For index matching, order matters - check if cols1 is prefix of cols2
        for i, col in enumerate(cols1):
            if i >= len(cols2):
                return False
            if col.lower() != cols2[i].lower():
                return False

        return True
