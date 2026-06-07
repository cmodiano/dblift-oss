"""SQL Insights using SqlGlot for enhanced logging and performance analysis.

This module provides advanced SQL analysis capabilities using sqlglot:
- Query complexity metrics
- Table and column dependency tracking
- Query optimization hints
- Performance predictions
- Detailed logging enhancements
"""

import logging
from typing import Any, Dict, List

try:
    from sqlglot import exp, parse_one

    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False

from db.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class SqlInsights:
    """Provides enhanced SQL analysis using sqlglot for logging and performance."""

    def __init__(self, dialect: str = "postgresql"):  # lint: allow-dialect-string: dialect dispatch
        """Initialize SQL insights analyzer.

        Args:
            dialect: SQL dialect (oracle, mysql, postgresql, sqlserver, db2)
        """
        self.dialect = dialect.lower()
        quirks = ProviderRegistry.get_quirks(self.dialect)
        self.sqlglot_dialect = quirks.sqlglot_dialect or "postgres"  # lint: allow-dialect-string
        self.available = SQLGLOT_AVAILABLE and quirks.sqlglot_dialect is not None

        if not self.available:
            logger.debug(f"SqlGlot insights not available for {self.dialect}")

    def analyze_query_complexity(self, sql: str) -> Dict[str, Any]:
        """Analyze query complexity and return metrics.

        Args:
            sql: SQL query to analyze

        Returns:
            Dict with complexity metrics:
            {
                'complexity_score': int,  # 0-100
                'join_count': int,
                'subquery_count': int,
                'cte_count': int,
                'aggregate_functions': List[str],
                'table_count': int,
                'estimated_cost': str,  # LOW, MEDIUM, HIGH
                'warnings': List[str]
            }
        """
        if not self.available:
            return self._empty_complexity()

        try:
            ast = parse_one(sql, read=self.sqlglot_dialect)

            # Count different query elements
            join_count = len(list(ast.find_all(exp.Join)))
            subquery_count = len(list(ast.find_all(exp.Subquery)))
            cte_count = len(list(ast.find_all(exp.CTE)))
            table_count = len(list(ast.find_all(exp.Table)))

            # Find aggregate functions
            aggregates = []
            for node in ast.find_all(exp.AggFunc):
                aggregates.append(node.__class__.__name__)

            # Calculate complexity score (0-100)
            complexity = 0
            complexity += min(join_count * 10, 30)  # Max 30 for joins
            complexity += min(subquery_count * 15, 30)  # Max 30 for subqueries
            complexity += min(cte_count * 5, 10)  # Max 10 for CTEs
            complexity += min(len(aggregates) * 5, 20)  # Max 20 for aggregates
            complexity += min((table_count - 1) * 5, 10)  # Max 10 for tables

            # Estimate cost
            if complexity < 25:
                cost = "LOW"
            elif complexity < 60:
                cost = "MEDIUM"
            else:
                cost = "HIGH"

            # Generate warnings
            warnings = []
            if join_count > 5:
                warnings.append(f"Many joins ({join_count}) - consider optimization")
            if subquery_count > 3:
                warnings.append(f"Multiple subqueries ({subquery_count}) - consider CTEs")
            if table_count > 10:
                warnings.append(f"Many tables ({table_count}) - verify query design")

            return {
                "complexity_score": min(complexity, 100),
                "join_count": join_count,
                "subquery_count": subquery_count,
                "cte_count": cte_count,
                "aggregate_functions": list(set(aggregates)),
                "table_count": table_count,
                "estimated_cost": cost,
                "warnings": warnings,
            }

        except Exception as e:
            logger.debug(f"Could not analyze query complexity: {e}")
            return self._empty_complexity()

    def extract_table_dependencies(self, sql: str) -> Dict[str, List[str]]:
        """Extract table and column dependencies from SQL.

        Args:
            sql: SQL statement to analyze

        Returns:
            Dict with dependencies:
            {
                'tables': List[str],
                'columns': List[str],  # Fully qualified (table.column)
                'schemas': List[str]
            }
        """
        if not self.available:
            return {"tables": [], "columns": [], "schemas": []}

        try:
            ast = parse_one(sql, read=self.sqlglot_dialect)

            tables = set()
            columns = set()
            schemas = set()

            # Extract tables
            for table in ast.find_all(exp.Table):
                if table.name:
                    tables.add(table.name)
                if table.db:
                    schemas.add(table.db)

            # Extract columns (for lineage tracking)
            for column in ast.find_all(exp.Column):
                col_name = column.name
                if column.table:
                    columns.add(f"{column.table}.{col_name}")
                else:
                    columns.add(col_name)

            return {
                "tables": sorted(list(tables)),
                "columns": sorted(list(columns)),
                "schemas": sorted(list(schemas)),
            }

        except Exception as e:
            logger.debug(f"Could not extract dependencies: {e}")
            return {"tables": [], "columns": [], "schemas": []}

    def get_query_type_details(self, sql: str) -> Dict[str, Any]:
        """Get detailed information about query type.

        Args:
            sql: SQL statement to analyze

        Returns:
            Dict with query details:
            {
                'type': str,  # SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, etc.
                'is_read_only': bool,
                'is_ddl': bool,
                'is_dml': bool,
                'affects_data': bool,
                'operation': str  # Human-readable description
            }
        """
        if not self.available:
            return self._empty_query_type()

        try:
            ast = parse_one(sql, read=self.sqlglot_dialect)

            query_type = ast.__class__.__name__
            is_ddl = isinstance(ast, (exp.Create, exp.Alter, exp.Drop))
            is_dml = isinstance(ast, (exp.Insert, exp.Update, exp.Delete, exp.Merge))
            is_query = isinstance(ast, (exp.Select, exp.Union, exp.Intersect, exp.Except))
            is_read_only = is_query
            affects_data = is_dml or is_ddl

            # Generate human-readable operation description
            if isinstance(ast, exp.Select):
                operation = "SELECT query"
            elif isinstance(ast, exp.Insert):
                operation = "INSERT data"
            elif isinstance(ast, exp.Update):
                operation = "UPDATE data"
            elif isinstance(ast, exp.Delete):
                operation = "DELETE data"
            elif isinstance(ast, exp.Create):
                kind = getattr(ast, "kind", "object")
                operation = f"CREATE {kind}"
            elif isinstance(ast, exp.Alter):
                operation = "ALTER object"
            elif isinstance(ast, exp.Drop):
                operation = "DROP object"
            else:
                operation = query_type

            return {
                "type": query_type,
                "is_read_only": is_read_only,
                "is_ddl": is_ddl,
                "is_dml": is_dml,
                "affects_data": affects_data,
                "operation": operation,
            }

        except Exception as e:
            logger.debug(f"Could not determine query type: {e}")
            return self._empty_query_type()

    def predict_performance_issues(self, sql: str) -> List[Dict[str, str]]:
        """Predict potential performance issues in the query.

        Args:
            sql: SQL query to analyze

        Returns:
            List of potential issues:
            [
                {
                    'severity': 'LOW|MEDIUM|HIGH',
                    'issue': 'Description of issue',
                    'suggestion': 'How to fix'
                }
            ]
        """
        if not self.available:
            return []

        issues = []

        try:
            ast = parse_one(sql, read=self.sqlglot_dialect)

            # Check for missing WHERE clause in UPDATE/DELETE
            if isinstance(ast, (exp.Update, exp.Delete)):
                where_clause = ast.find(exp.Where)
                if not where_clause:
                    issues.append(
                        {
                            "severity": "HIGH",
                            "issue": f"{ast.__class__.__name__} without WHERE clause",
                            "suggestion": "Add WHERE clause to avoid full table modification",
                        }
                    )

            # Check for SELECT *
            if isinstance(ast, exp.Select):
                for select_expr in ast.expressions:
                    if isinstance(select_expr, exp.Star):
                        issues.append(
                            {
                                "severity": "LOW",
                                "issue": "SELECT * used",
                                "suggestion": "Specify explicit columns for better performance",
                            }
                        )
                        break

            # Check for complex subqueries without indexes
            subqueries = list(ast.find_all(exp.Subquery))
            if len(subqueries) > 2:
                issues.append(
                    {
                        "severity": "MEDIUM",
                        "issue": f"Multiple subqueries detected ({len(subqueries)})",
                        "suggestion": "Consider using CTEs (WITH clause) for better readability and potential optimization",
                    }
                )

            # Check for DISTINCT with many columns
            if isinstance(ast, exp.Select) and ast.find(exp.Distinct):
                column_count = len(list(ast.find_all(exp.Column)))
                if column_count > 5:
                    issues.append(
                        {
                            "severity": "MEDIUM",
                            "issue": "DISTINCT with many columns",
                            "suggestion": "Ensure proper indexes exist or reconsider query design",
                        }
                    )

            # Check for UNION instead of UNION ALL
            unions = list(ast.find_all(exp.Union))
            for union in unions:
                if not union.args.get("distinct"):  # UNION implies DISTINCT
                    issues.append(
                        {
                            "severity": "LOW",
                            "issue": "UNION used (implies DISTINCT)",
                            "suggestion": "Use UNION ALL if duplicates are acceptable for better performance",
                        }
                    )

        except Exception as e:
            logger.debug(f"Could not predict performance issues: {e}")

        return issues

    def generate_execution_plan_hints(self, sql: str) -> Dict[str, Any]:
        """Generate hints for better query execution.

        Args:
            sql: SQL query to analyze

        Returns:
            Dict with execution hints:
            {
                'index_suggestions': List[str],
                'optimization_hints': List[str],
                'caching_strategy': str,
                'parallelization_potential': str
            }
        """
        if not self.available:
            return {
                "index_suggestions": [],
                "optimization_hints": [],
                "caching_strategy": "NONE",
                "parallelization_potential": "UNKNOWN",
            }

        try:
            complexity = self.analyze_query_complexity(sql)
            deps = self.extract_table_dependencies(sql)

            # Generate index suggestions based on tables accessed
            index_suggestions = []
            if deps["tables"]:
                for table in deps["tables"][:5]:  # Limit to 5 tables
                    index_suggestions.append(f"Consider index on {table} for join/filter columns")

            # Generate optimization hints
            optimization_hints = []
            if complexity["join_count"] > 3:
                optimization_hints.append(
                    "Consider breaking into smaller queries or using materialized views"
                )
            if complexity["subquery_count"] > 2:
                optimization_hints.append("Convert subqueries to CTEs for better optimization")
            if complexity["table_count"] > 10:
                optimization_hints.append("Review query design - many tables involved")

            # Caching strategy
            if complexity["complexity_score"] > 70:
                caching_strategy = "HIGH - Consider result caching"
            elif complexity["complexity_score"] > 40:
                caching_strategy = "MEDIUM - May benefit from caching"
            else:
                caching_strategy = "LOW - Simple query, caching may not help"

            # Parallelization potential
            if complexity["join_count"] > 5 or complexity["table_count"] > 8:
                parallelization_potential = "HIGH - May benefit from parallel execution"
            elif complexity["join_count"] > 2:
                parallelization_potential = "MEDIUM"
            else:
                parallelization_potential = "LOW"

            return {
                "index_suggestions": index_suggestions,
                "optimization_hints": optimization_hints,
                "caching_strategy": caching_strategy,
                "parallelization_potential": parallelization_potential,
            }

        except Exception as e:
            logger.debug(f"Could not generate execution hints: {e}")
            return {
                "index_suggestions": [],
                "optimization_hints": [],
                "caching_strategy": "NONE",
                "parallelization_potential": "UNKNOWN",
            }

    def format_sql_for_logging(self, sql: str, max_length: int = 200) -> str:
        """Format SQL for logging with intelligent truncation.

        Args:
            sql: SQL to format
            max_length: Maximum length for log output

        Returns:
            Formatted SQL string
        """
        if not self.available:
            # Fallback to simple truncation
            sql_clean = " ".join(sql.split())
            if len(sql_clean) > max_length:
                return sql_clean[:max_length] + "..."
            return sql_clean

        try:
            # Try to pretty-print with sqlglot
            ast = parse_one(sql, read=self.sqlglot_dialect)
            formatted = ast.sql(dialect=self.sqlglot_dialect, pretty=True)

            # Truncate if needed
            if len(formatted) > max_length:
                # Try to keep first line (usually the operation)
                first_line = formatted.split("\n")[0]
                if len(first_line) <= max_length:
                    return str(first_line + " ...")
                return str(formatted[:max_length] + "...")

            return str(formatted)

        except Exception as e:
            logger.debug(f"sqlglot formatting failed, using simple fallback: {e}")
            # Fallback to simple formatting
            sql_clean = " ".join(sql.split())
            if len(sql_clean) > max_length:
                return sql_clean[:max_length] + "..."
            return sql_clean

    def _empty_complexity(self) -> Dict[str, Any]:
        """Return empty complexity metrics."""
        return {
            "complexity_score": 0,
            "join_count": 0,
            "subquery_count": 0,
            "cte_count": 0,
            "aggregate_functions": [],
            "table_count": 0,
            "estimated_cost": "UNKNOWN",
            "warnings": [],
        }

    def _empty_query_type(self) -> Dict[str, Any]:
        """Return empty query type details."""
        return {
            "type": "UNKNOWN",
            "is_read_only": False,
            "is_ddl": False,
            "is_dml": False,
            "affects_data": False,
            "operation": "UNKNOWN",
        }
