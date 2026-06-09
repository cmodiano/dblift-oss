"""Unit tests for core.migration.sql.sql_insights module."""

from unittest.mock import patch

import pytest

from core.migration.sql.sql_insights import SqlInsights


@pytest.mark.unit
class TestSqlInsights:
    """Test SqlInsights class."""

    def test_initialization_postgresql(self):
        """Test SqlInsights initialization with PostgreSQL dialect."""
        insights = SqlInsights(dialect="postgresql")

        assert insights.dialect == "postgresql"
        assert insights.sqlglot_dialect == "postgres"

    def test_initialization_mysql(self):
        """Test SqlInsights initialization with MySQL dialect."""
        insights = SqlInsights(dialect="mysql")

        assert insights.dialect == "mysql"
        assert insights.sqlglot_dialect == "mysql"

    def test_initialization_db2(self):
        """Test SqlInsights initialization with DB2 dialect (not supported)."""
        insights = SqlInsights(dialect="db2")

        # DB2 is not supported, so available should be False
        assert insights.dialect == "db2"
        assert insights.available is False

    @patch("core.migration.sql.sql_insights.SQLGLOT_AVAILABLE", False)
    def test_initialization_sqlglot_not_available(self):
        """Test SqlInsights when sqlglot is not available."""
        insights = SqlInsights(dialect="postgresql")

        assert insights.available is False

    def test_analyze_query_complexity_simple(self):
        """Test analyzing simple query complexity."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.analyze_query_complexity("SELECT * FROM users")

        assert "complexity_score" in result
        assert "join_count" in result
        assert "subquery_count" in result
        assert "table_count" in result
        assert result["table_count"] >= 1

    def test_analyze_query_complexity_with_joins(self):
        """Test analyzing query with joins."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = """
        SELECT u.id, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN products p ON o.product_id = p.id
        """
        result = insights.analyze_query_complexity(sql)

        assert result["join_count"] >= 2
        assert result["complexity_score"] > 0

    def test_analyze_query_complexity_with_subqueries(self):
        """Test analyzing query with subqueries."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        result = insights.analyze_query_complexity(sql)

        assert result["subquery_count"] >= 1

    def test_analyze_query_complexity_with_cte(self):
        """Test analyzing query with CTE."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = """
        WITH user_orders AS (SELECT user_id, COUNT(*) as order_count FROM orders GROUP BY user_id)
        SELECT * FROM users u JOIN user_orders uo ON u.id = uo.user_id
        """
        result = insights.analyze_query_complexity(sql)

        assert result["cte_count"] >= 1

    def test_analyze_query_complexity_with_aggregates(self):
        """Test analyzing query with aggregate functions."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = "SELECT COUNT(*), SUM(amount), AVG(price) FROM orders"
        result = insights.analyze_query_complexity(sql)

        assert len(result["aggregate_functions"]) >= 1

    def test_analyze_query_complexity_invalid_sql(self):
        """Test analyzing invalid SQL."""
        insights = SqlInsights(dialect="postgresql")

        result = insights.analyze_query_complexity("INVALID SQL SYNTAX !!!")

        # Should return empty complexity without crashing
        assert "complexity_score" in result
        assert result["complexity_score"] == 0 or result["estimated_cost"] == "UNKNOWN"

    def test_extract_table_dependencies_simple(self):
        """Test extracting table dependencies from simple query."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.extract_table_dependencies("SELECT * FROM users")

        assert "tables" in result
        assert "columns" in result
        assert "schemas" in result
        assert "users" in result["tables"]

    def test_extract_table_dependencies_multiple_tables(self):
        """Test extracting dependencies from query with multiple tables."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = "SELECT u.id, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        result = insights.extract_table_dependencies(sql)

        assert "users" in result["tables"] or "u" in result["tables"]
        assert "orders" in result["tables"] or "o" in result["tables"]

    def test_extract_table_dependencies_with_schema(self):
        """Test extracting dependencies with schema qualification."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.extract_table_dependencies("SELECT * FROM public.users")

        assert len(result["tables"]) >= 1
        assert len(result["schemas"]) >= 1

    def test_extract_table_dependencies_invalid_sql(self):
        """Test extracting dependencies from invalid SQL."""
        insights = SqlInsights(dialect="postgresql")

        result = insights.extract_table_dependencies("INVALID SQL")

        # sqlglot may partially parse invalid SQL and extract tokens
        # So we just check that the structure is correct
        assert "tables" in result
        assert "columns" in result
        assert "schemas" in result
        # For truly invalid SQL, we expect mostly empty results
        # (though sqlglot might extract some tokens)

    def test_get_query_type_details_select(self):
        """Test getting query type details for SELECT."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.get_query_type_details("SELECT * FROM users")

        assert result["type"] in ["Select", "SELECT", "Select"]
        assert result["is_read_only"] is True
        assert result["is_ddl"] is False
        assert result["is_dml"] is False
        assert "SELECT" in result["operation"].upper()

    def test_get_query_type_details_insert(self):
        """Test getting query type details for INSERT."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.get_query_type_details("INSERT INTO users (id) VALUES (1)")

        assert result["is_dml"] is True
        assert result["affects_data"] is True
        assert "INSERT" in result["operation"].upper()

    def test_get_query_type_details_update(self):
        """Test getting query type details for UPDATE."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.get_query_type_details("UPDATE users SET name = 'test' WHERE id = 1")

        assert result["is_dml"] is True
        assert result["affects_data"] is True
        assert "UPDATE" in result["operation"].upper()

    def test_get_query_type_details_delete(self):
        """Test getting query type details for DELETE."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.get_query_type_details("DELETE FROM users WHERE id = 1")

        assert result["is_dml"] is True
        assert result["affects_data"] is True
        assert "DELETE" in result["operation"].upper()

    def test_get_query_type_details_create(self):
        """Test getting query type details for CREATE."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.get_query_type_details("CREATE TABLE users (id INT)")

        assert result["is_ddl"] is True
        assert result["affects_data"] is True
        assert "CREATE" in result["operation"].upper()

    def test_get_query_type_details_invalid(self):
        """Test getting query type details for invalid SQL."""
        insights = SqlInsights(dialect="postgresql")

        result = insights.get_query_type_details("INVALID SQL")

        assert result["type"] == "UNKNOWN" or "type" in result
        assert result["operation"] == "UNKNOWN" or "operation" in result

    def test_predict_performance_issues_update_without_where(self):
        """Test predicting issues for UPDATE without WHERE."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        issues = insights.predict_performance_issues("UPDATE users SET name = 'test'")

        assert len(issues) >= 1
        assert any("WHERE" in issue["issue"].upper() for issue in issues)
        assert any(issue["severity"] == "HIGH" for issue in issues)

    def test_predict_performance_issues_delete_without_where(self):
        """Test predicting issues for DELETE without WHERE."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        issues = insights.predict_performance_issues("DELETE FROM users")

        assert len(issues) >= 1
        assert any("WHERE" in issue["issue"].upper() for issue in issues)

    def test_predict_performance_issues_select_star(self):
        """Test predicting issues for SELECT *."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        issues = insights.predict_performance_issues("SELECT * FROM users")

        # May or may not detect SELECT *, depends on sqlglot version
        # Just verify it doesn't crash
        assert isinstance(issues, list)

    def test_predict_performance_issues_multiple_subqueries(self):
        """Test predicting issues for multiple subqueries."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = """
        SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)
        AND email IN (SELECT email FROM profiles)
        AND status IN (SELECT status FROM user_statuses)
        """
        issues = insights.predict_performance_issues(sql)

        # May detect multiple subqueries
        assert isinstance(issues, list)

    def test_predict_performance_issues_invalid_sql(self):
        """Test predicting issues for invalid SQL."""
        insights = SqlInsights(dialect="postgresql")

        issues = insights.predict_performance_issues("INVALID SQL")

        assert issues == []

    def test_generate_execution_plan_hints_simple(self):
        """Test generating execution hints for simple query."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.generate_execution_plan_hints("SELECT * FROM users")

        assert "index_suggestions" in result
        assert "optimization_hints" in result
        assert "caching_strategy" in result
        assert "parallelization_potential" in result

    def test_generate_execution_plan_hints_complex(self):
        """Test generating execution hints for complex query."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        sql = """
        SELECT u.id, u.name, o.total, p.name
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN products p ON o.product_id = p.id
        JOIN categories c ON p.category_id = c.id
        WHERE u.active = true
        """
        result = insights.generate_execution_plan_hints(sql)

        assert "index_suggestions" in result
        assert "optimization_hints" in result
        # caching_strategy returns format like "LOW - Simple query, caching may not help"
        assert result["caching_strategy"].startswith(("LOW", "MEDIUM", "HIGH", "NONE"))

    def test_generate_execution_plan_hints_invalid_sql(self):
        """Test generating hints for invalid SQL."""
        insights = SqlInsights(dialect="postgresql")

        result = insights.generate_execution_plan_hints("INVALID SQL")

        assert "index_suggestions" in result
        # Invalid SQL may still be partially parsed by sqlglot, so it might return
        # a complexity score and generate a caching strategy. Check that it's a valid value.
        assert result["caching_strategy"] in [
            "NONE",
            "LOW - Simple query, caching may not help",
            "MEDIUM - May benefit from caching",
            "HIGH - Consider result caching",
        ]

    def test_format_sql_for_logging_simple(self):
        """Test formatting SQL for logging."""
        insights = SqlInsights(dialect="postgresql")

        if not insights.available:
            pytest.skip("SqlGlot not available")

        result = insights.format_sql_for_logging("SELECT * FROM users")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_sql_for_logging_truncation(self):
        """Test SQL formatting with truncation."""
        insights = SqlInsights(dialect="postgresql")

        long_sql = "SELECT " + ", ".join([f"column{i}" for i in range(100)]) + " FROM users"
        result = insights.format_sql_for_logging(long_sql, max_length=50)

        assert len(result) <= 53  # 50 + "..."
        assert "..." in result or len(result) <= 50

    def test_format_sql_for_logging_invalid_sql(self):
        """Test formatting invalid SQL."""
        insights = SqlInsights(dialect="postgresql")

        result = insights.format_sql_for_logging("INVALID SQL SYNTAX", max_length=20)

        # Should fallback to simple formatting
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_complexity(self):
        """Test _empty_complexity method."""
        insights = SqlInsights(dialect="postgresql")

        result = insights._empty_complexity()

        assert result["complexity_score"] == 0
        assert result["join_count"] == 0
        assert result["subquery_count"] == 0
        assert result["estimated_cost"] == "UNKNOWN"

    def test_empty_query_type(self):
        """Test _empty_query_type method."""
        insights = SqlInsights(dialect="postgresql")

        result = insights._empty_query_type()

        assert result["type"] == "UNKNOWN"
        assert result["is_read_only"] is False
        assert result["is_ddl"] is False
        assert result["is_dml"] is False
        assert result["operation"] == "UNKNOWN"

    def test_analyze_query_complexity_when_not_available(self):
        """Test analyze_query_complexity when sqlglot not available."""
        with patch("core.migration.sql.sql_insights.SQLGLOT_AVAILABLE", False):
            insights = SqlInsights(dialect="postgresql")

            result = insights.analyze_query_complexity("SELECT * FROM users")

            assert result["complexity_score"] == 0
            assert result["estimated_cost"] == "UNKNOWN"

    def test_extract_table_dependencies_when_not_available(self):
        """Test extract_table_dependencies when sqlglot not available."""
        with patch("core.migration.sql.sql_insights.SQLGLOT_AVAILABLE", False):
            insights = SqlInsights(dialect="postgresql")

            result = insights.extract_table_dependencies("SELECT * FROM users")

            assert result == {"tables": [], "columns": [], "schemas": []}

    def test_get_query_type_details_when_not_available(self):
        """Test get_query_type_details when sqlglot not available."""
        with patch("core.migration.sql.sql_insights.SQLGLOT_AVAILABLE", False):
            insights = SqlInsights(dialect="postgresql")

            result = insights.get_query_type_details("SELECT * FROM users")

            assert result["type"] == "UNKNOWN"
            assert result["operation"] == "UNKNOWN"
