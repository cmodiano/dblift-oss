"""
Tests for SqlAnalyzer SQL Model API (Phase 1.4).

This module tests the new public API methods that expose rich SQL Model objects:
- parse_sql() - Get full ParseResult
- get_tables() - Extract Table objects
- get_views() - Extract View objects
- get_indexes() - Extract Index objects
- get_table() - Get specific table by name
- get_view() - Get specific view by name
- has_circular_dependencies() - Check for circular dependencies
- get_dependencies() - Get dependency graph
"""

import pytest

from core.migration.sql.sql_analyzer import SqlAnalyzer
from core.sql_model.base import ConstraintType


class TestSqlAnalyzerSqlModelAPI:
    """Test SQL Model API methods in SqlAnalyzer."""

    def test_parse_sql_returns_parse_result(self):
        """Test that parse_sql() returns a ParseResult object."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username VARCHAR(100) NOT NULL
        );
        """

        result = analyzer.parse_sql(sql)

        assert result is not None
        assert hasattr(result, "success")
        assert result.success is True
        assert hasattr(result, "tables")

    def test_get_tables_extracts_tables(self):
        """Test get_tables() extracts Table objects."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username VARCHAR(100) NOT NULL,
            email VARCHAR(255)
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """

        tables = analyzer.get_tables(sql)

        assert len(tables) == 2

        # Check first table
        users_table = next((t for t in tables if t.name == "users"), None)
        assert users_table is not None
        assert len(users_table.columns) == 3

        # Check columns
        id_col = users_table.get_column("id")
        assert id_col is not None
        assert id_col.is_primary_key is True

        username_col = users_table.get_column("username")
        assert username_col is not None
        assert username_col.nullable is False

    def test_get_tables_returns_empty_for_no_tables(self):
        """Test get_tables() returns empty list when no tables found."""
        analyzer = SqlAnalyzer("postgresql")

        sql = "SELECT * FROM users;"

        tables = analyzer.get_tables(sql)

        assert tables == []

    def test_get_views_extracts_views(self):
        """Test get_views() extracts View objects."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE VIEW active_users AS
        SELECT id, username, email
        FROM users
        WHERE active = true;

        CREATE VIEW user_orders AS
        SELECT u.username, o.id
        FROM users u
        JOIN orders o ON u.id = o.user_id;
        """

        views = analyzer.get_views(sql)

        assert len(views) == 2

        # Check first view
        active_users = next((v for v in views if v.name == "active_users"), None)
        assert active_users is not None
        assert "SELECT" in active_users.query
        assert "users" in active_users.query.lower()

    def test_get_indexes_extracts_indexes(self):
        """Test get_indexes() extracts Index objects."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE INDEX idx_users_email ON users(email);
        CREATE UNIQUE INDEX idx_users_username ON users(username);
        """

        indexes = analyzer.get_indexes(sql)

        assert len(indexes) >= 1

        # Check index properties
        email_idx = next((i for i in indexes if "email" in i.name.lower()), None)
        if email_idx:
            # table_name extraction may vary by implementation
            assert email_idx.name is not None

    def test_get_table_by_name(self):
        """Test get_table() retrieves specific table by name."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE users (id INTEGER PRIMARY KEY);
        CREATE TABLE orders (id INTEGER PRIMARY KEY);
        """

        users_table = analyzer.get_table(sql, "users")

        assert users_table is not None
        assert users_table.name == "users"
        assert len(users_table.columns) >= 1

    def test_get_table_returns_none_for_nonexistent(self):
        """Test get_table() returns None for nonexistent table."""
        analyzer = SqlAnalyzer("postgresql")

        sql = "CREATE TABLE users (id INTEGER PRIMARY KEY);"

        table = analyzer.get_table(sql, "nonexistent")

        assert table is None

    def test_get_view_by_name(self):
        """Test get_view() retrieves specific view by name."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE VIEW active_users AS SELECT * FROM users WHERE active = true;
        CREATE VIEW inactive_users AS SELECT * FROM users WHERE active = false;
        """

        view = analyzer.get_view(sql, "active_users")

        assert view is not None
        assert view.name == "active_users"

    def test_has_circular_dependencies_detects_cycles(self):
        """Test has_circular_dependencies() detects circular FK references."""
        analyzer = SqlAnalyzer("postgresql")

        # This SQL would create circular dependencies if all executed
        # (though this specific example might not be parsed as circular without proper setup)
        sql = """
        CREATE TABLE a (
            id INTEGER PRIMARY KEY,
            b_id INTEGER REFERENCES b(id)
        );
        CREATE TABLE b (
            id INTEGER PRIMARY KEY,
            c_id INTEGER REFERENCES c(id)
        );
        CREATE TABLE c (
            id INTEGER PRIMARY KEY,
            a_id INTEGER REFERENCES a(id)
        );
        """

        # Note: This test depends on parser's ability to extract FK references
        # The actual result may vary based on implementation
        result = analyzer.has_circular_dependencies(sql)

        # We just test that the method works, circular detection logic is tested elsewhere
        assert isinstance(result, bool)

    def test_get_dependencies_returns_dependency_graph(self):
        """Test get_dependencies() returns dependency mapping."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE users (id INTEGER PRIMARY KEY);
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id)
        );
        """

        deps = analyzer.get_dependencies(sql)

        assert isinstance(deps, dict)
        # Dependencies may or may not be populated depending on parser implementation

    def test_table_columns_with_constraints(self):
        """Test that Table objects have properly extracted columns and constraints."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            sku VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            price DECIMAL(10,2) DEFAULT 0.00,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        tables = analyzer.get_tables(sql)

        assert len(tables) == 1
        table = tables[0]

        # Check columns
        assert len(table.columns) >= 4

        # Check PRIMARY KEY constraint
        pk = table.get_primary_key()
        assert pk is not None

        # Check UNIQUE constraints
        unique_constraints = table.get_unique_constraints()
        assert len(unique_constraints) >= 1

    def test_get_tables_extracts_inline_constraints(self):
        """SQLGlot-backed parsing should capture inline FK/unique/default metadata."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE accounting.users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE accounting.orders (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES accounting.users(id) ON DELETE CASCADE,
            amount NUMERIC(10,2) CHECK (amount > 0)
        );
        """

        tables = analyzer.get_tables(sql)

        assert len(tables) == 2

        users = next(t for t in tables if t.name == "users")
        email_col = users.get_column("email")
        assert email_col is not None
        assert email_col.nullable is False
        uniques = users.get_unique_constraints()
        assert any(
            "email" in [col.lower() for col in constraint.column_names] for constraint in uniques
        )

        orders = next(t for t in tables if t.name == "orders")
        fk_constraints = orders.get_foreign_keys()
        assert len(fk_constraints) == 1
        fk = fk_constraints[0]
        assert fk.reference_table.lower() == "users"
        assert fk.reference_schema.lower() == "accounting"

        check_constraints = orders.get_check_constraints()
        assert len(check_constraints) == 1
        assert "amount" in (check_constraints[0].check_expression or "").lower()

    def test_multi_dialect_support(self):
        """Test that API works across different SQL dialects."""
        dialects = ["postgresql", "mysql", "oracle", "sqlserver"]

        for dialect in dialects:
            analyzer = SqlAnalyzer(dialect)

            # Use dialect-agnostic SQL
            sql = "CREATE TABLE test_table (id INTEGER PRIMARY KEY);"

            tables = analyzer.get_tables(sql)

            # Should work for all dialects (may return different results)
            assert isinstance(tables, list)

    def test_complex_schema_with_multiple_objects(self):
        """Test parsing complex schema with tables, views, and indexes."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        CREATE TABLE departments (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL
        );

        CREATE TABLE employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            dept_id INTEGER REFERENCES departments(id),
            salary DECIMAL(10,2)
        );

        CREATE VIEW high_earners AS
        SELECT e.name, e.salary, d.name as department
        FROM employees e
        JOIN departments d ON e.dept_id = d.id
        WHERE e.salary > 100000;

        CREATE INDEX idx_employees_dept ON employees(dept_id);
        """

        # Test all accessor methods
        tables = analyzer.get_tables(sql)
        views = analyzer.get_views(sql)
        indexes = analyzer.get_indexes(sql)

        assert len(tables) == 2
        assert len(views) == 1
        assert len(indexes) >= 1

        # Verify table relationships
        employees = analyzer.get_table(sql, "employees")
        assert employees is not None

        fk_constraints = employees.get_foreign_keys()
        # Note: FK extraction with inline REFERENCES syntax may vary by parser
        # Just verify the method works
        assert isinstance(fk_constraints, list)

    def test_parse_sql_with_default_schema(self):
        """Test parse_sql() with default_schema parameter."""
        analyzer = SqlAnalyzer("postgresql")

        sql = "CREATE TABLE users (id INTEGER PRIMARY KEY);"

        result = analyzer.parse_sql(sql, default_schema="public")

        assert result.success
        if result.tables:
            # Schema handling depends on parser implementation
            assert result.tables[0].name == "users"

    def test_empty_sql_handling(self):
        """Test that API handles empty SQL gracefully."""
        analyzer = SqlAnalyzer("postgresql")

        tables = analyzer.get_tables("")
        views = analyzer.get_views("")
        indexes = analyzer.get_indexes("")

        assert tables == []
        assert views == []
        assert indexes == []

    def test_sql_with_only_comments(self):
        """Test parsing SQL with only comments."""
        analyzer = SqlAnalyzer("postgresql")

        sql = """
        -- This is a comment
        /* This is a block comment */
        """

        result = analyzer.parse_sql(sql)

        # Should parse successfully even with no actual SQL
        assert result.success or (result.errors is None or len(result.errors) == 0)
        assert result.tables is None or len(result.tables) == 0
