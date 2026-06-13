"""Tests for SQL model View class."""

from unittest.mock import Mock, patch

import pytest

from core.sql_model.base import SqlObjectType
from core.sql_model.view import View
from core.sql_model.view_options import PostgresViewOptions, ViewOptions


@pytest.mark.unit
class TestView:
    """Test View SQL model class."""

    def test_view_initialization_basic(self):
        """Test basic view initialization."""
        view = View("test_view")

        assert view.name == "test_view"
        assert view.schema is None
        assert view.query is None
        assert view.columns == []
        assert view.materialized is False
        assert view.object_type == SqlObjectType.VIEW
        assert view.dialect is None

    def test_view_initialization_with_all_params(self):
        """Test view initialization with all parameters."""
        columns = ["col1", "col2", "col3"]
        query = "SELECT * FROM test_table"

        view = View(
            name="test_view",
            schema="test_schema",
            query=query,
            columns=columns,
            materialized=False,
            dialect="postgresql",
        )

        assert view.name == "test_view"
        assert view.schema == "test_schema"
        assert view.query == query
        assert view.columns == columns
        assert view.materialized is False
        assert view.object_type == SqlObjectType.VIEW
        assert view.dialect == "postgresql"

    def test_materialized_view_initialization(self):
        """Test materialized view initialization."""
        view = View(name="test_mv", schema="test_schema", materialized=True)

        assert view.name == "test_mv"
        assert view.materialized is True
        assert view.object_type == SqlObjectType.MATERIALIZED_VIEW

    def test_create_statement_basic_view(self):
        """Test CREATE VIEW statement generation for basic view."""
        view = View(name="test_view", query="SELECT id, name FROM users")

        result = view.create_statement

        assert "CREATE VIEW test_view" in result
        assert "AS" in result
        assert "SELECT id, name FROM users" in result

    def test_create_statement_with_schema(self):
        """Test CREATE VIEW statement with schema."""
        view = View(name="test_view", schema="test_schema", query="SELECT * FROM users")

        result = view.create_statement

        assert "CREATE VIEW test_schema.test_view" in result
        assert "AS" in result
        assert "SELECT * FROM users" in result

    def test_create_statement_with_columns(self):
        """Test CREATE VIEW statement with specified columns."""
        view = View(
            name="test_view", query="SELECT id, name FROM users", columns=["user_id", "user_name"]
        )

        result = view.create_statement

        assert "CREATE VIEW test_view (user_id, user_name)" in result
        assert "AS" in result
        assert "SELECT id, name FROM users" in result

    def test_create_statement_materialized_view_basic(self):
        """Test CREATE MATERIALIZED VIEW statement."""
        view = View(name="test_mv", query="SELECT * FROM users", materialized=True)

        result = view.create_statement

        assert "CREATE MATERIALIZED VIEW test_mv" in result
        assert "AS" in result
        assert "SELECT * FROM users" in result

    def test_create_statement_no_query(self):
        """Test CREATE VIEW statement when no query is provided."""
        view = View(name="test_view")

        result = view.create_statement

        assert "CREATE VIEW" in result
        assert "test_view" in result
        # Should not contain AS when no query is provided
        assert "AS" not in result

    def test_create_statement_empty_columns_list(self):
        """Test CREATE VIEW statement with empty columns list."""
        view = View(name="test_view", query="SELECT * FROM users", columns=[])

        result = view.create_statement

        assert "CREATE VIEW test_view" in result
        assert "(" not in result  # No column list should be included
        assert "AS" in result

    @patch.object(View, "format_identifier")
    def test_create_statement_uses_format_identifier(self, mock_format):
        """Test that create_statement uses format_identifier for names."""
        mock_format.side_effect = lambda x: f'"{x}"' if x else x

        view = View(name="test_view", schema="test_schema", columns=["col1", "col2"])

        result = view.create_statement

        # Verify format_identifier was called for schema, view name, and columns
        expected_calls = ["test_schema", "test_view", "col1", "col2"]
        actual_calls = [call[0][0] for call in mock_format.call_args_list]

        for expected in expected_calls:
            assert expected in actual_calls

    def test_str_representation(self):
        """Test string representation of view."""
        view = View(name="test_view", query="SELECT * FROM users")

        result = str(view)

        # Should return the same as create_statement
        assert result == view.create_statement
        assert "CREATE VIEW test_view" in result

    def test_from_dict_basic(self):
        """Test creating view from dictionary."""
        data = {
            "name": "test_view",
            "schema": "test_schema",
            "query": "SELECT * FROM users",
            "columns": ["id", "name"],
            "materialized": False,
            "dialect": "postgresql",
        }

        view = View.from_dict(data)

        assert view.name == "test_view"
        assert view.schema == "test_schema"
        assert view.query == "SELECT * FROM users"
        assert view.columns == ["id", "name"]
        assert view.materialized is False
        assert view.dialect == "postgresql"

    def test_from_dict_minimal(self):
        """Test creating view from minimal dictionary."""
        data = {"name": "simple_view"}

        view = View.from_dict(data)

        assert view.name == "simple_view"
        assert view.schema is None
        assert view.query is None
        assert view.columns == []
        assert view.materialized is False
        assert view.dialect is None

    def test_from_dict_materialized(self):
        """Test creating materialized view from dictionary."""
        data = {"name": "test_mv", "materialized": True}

        view = View.from_dict(data)

        assert view.name == "test_mv"
        assert view.materialized is True
        assert view.object_type == SqlObjectType.MATERIALIZED_VIEW

    def test_from_dict_with_default_values(self):
        """Test from_dict with various default values."""
        data = {
            "name": "test_view",
            "schema": "test_schema",
            # Missing columns, materialized, dialect, query
        }

        view = View.from_dict(data)

        assert view.name == "test_view"
        assert view.schema == "test_schema"
        assert view.query is None
        assert view.columns == []  # Default empty list
        assert view.materialized is False  # Default False
        assert view.dialect is None

    def test_to_dict_complete(self):
        """Test converting view to dictionary."""
        view = View(
            name="test_view",
            schema="test_schema",
            query="SELECT * FROM users",
            columns=["id", "name"],
            materialized=False,
            dialect="postgresql",
        )

        result = view.to_dict()

        expected = {
            "name": "test_view",
            "schema": "test_schema",
            "object_type": SqlObjectType.VIEW.value,
            "dialect": "postgresql",
            "query": "SELECT * FROM users",
            "columns": ["id", "name"],
            "materialized": False,
        }

        assert result == expected

    def test_to_dict_materialized_view(self):
        """Test converting materialized view to dictionary."""
        view = View(name="test_mv", materialized=True, dialect="oracle")

        result = view.to_dict()

        assert result["name"] == "test_mv"
        assert result["materialized"] is True
        assert result["object_type"] == SqlObjectType.MATERIALIZED_VIEW.value
        assert result["dialect"] == "oracle"
        assert result["schema"] is None
        assert result["query"] is None
        assert result["columns"] == []

    def test_to_dict_minimal(self):
        """Test converting minimal view to dictionary."""
        view = View(name="simple_view")

        result = view.to_dict()

        expected = {
            "name": "simple_view",
            "schema": None,
            "object_type": SqlObjectType.VIEW.value,
            "dialect": None,
            "query": None,
            "columns": [],
            "materialized": False,
        }

        assert result == expected

    def test_round_trip_serialization(self):
        """Test round-trip serialization (to_dict -> from_dict)."""
        original = View(
            name="test_view",
            schema="test_schema",
            query="SELECT id, name FROM users WHERE active = 1",
            columns=["user_id", "user_name"],
            materialized=True,
            dialect="oracle",
        )

        # Convert to dict and back
        data = original.to_dict()
        restored = View.from_dict(data)

        # Compare all attributes
        assert restored.name == original.name
        assert restored.schema == original.schema
        assert restored.query == original.query
        assert restored.columns == original.columns
        assert restored.materialized == original.materialized
        assert restored.dialect == original.dialect
        assert restored.object_type == original.object_type

    def test_inheritance_from_sql_object(self):
        """Test that View properly inherits from SqlObject."""
        view = View("test_view", schema="test_schema")

        # Should have inherited properties
        assert hasattr(view, "name")
        assert hasattr(view, "schema")
        assert hasattr(view, "object_type")
        assert hasattr(view, "dialect")

        # Should have inherited methods
        assert hasattr(view, "format_identifier")
        assert callable(view.format_identifier)

    def test_view_with_special_characters_in_name(self):
        """Test view with special characters in name."""
        view = View(name="user-summary_view", schema="test_schema", query="SELECT * FROM users")

        result = view.create_statement

        # Should handle the name properly
        assert "user-summary_view" in result
        assert "CREATE VIEW test_schema.user-summary_view" in result

    def test_view_with_complex_query(self):
        """Test view with complex multi-line query."""
        complex_query = """SELECT 
    u.id,
    u.name,
    u.email,
    COUNT(o.id) as order_count,
    SUM(o.total) as total_spent
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.active = 1
GROUP BY u.id, u.name, u.email
ORDER BY total_spent DESC"""

        view = View(
            name="user_analytics",
            schema="analytics",
            query=complex_query,
            columns=["user_id", "user_name", "email", "orders", "revenue"],
        )

        result = view.create_statement

        assert (
            "CREATE VIEW analytics.user_analytics (user_id, user_name, email, orders, revenue)"
            in result
        )
        assert "AS" in result
        assert "SELECT" in result
        assert "FROM users u" in result
        assert "GROUP BY" in result

    def test_none_values_handling(self):
        """Test handling of None values in various fields."""
        view = View(name="test_view", schema=None, query=None, columns=None, dialect=None)

        assert view.schema is None
        assert view.query is None
        assert view.columns == []  # Should default to empty list
        assert view.dialect is None

        # Should still generate a basic statement
        result = view.create_statement
        assert "CREATE VIEW test_view" in result

    def test_view_with_security_definer(self):
        """Test view with security_definer property."""
        view = View.from_options(
            name="secure_view",
            query="SELECT * FROM sensitive_data",
            dialect="postgresql",
            options=ViewOptions(postgres=PostgresViewOptions(security_definer=True)),
        )

        assert view.security_definer is True
        # Test that property is set correctly
        # Note: SQL generation may use generators that don't include security yet
        # This test verifies the property is stored correctly
        stmt = view._generate_basic_create_statement()
        assert "security_definer=true" in stmt.lower()

    def test_view_with_security_invoker(self):
        """Test view with security_invoker property."""
        view = View.from_options(
            name="secure_view",
            query="SELECT * FROM data",
            dialect="postgresql",
            options=ViewOptions(postgres=PostgresViewOptions(security_invoker=True)),
        )

        assert view.security_invoker is True
        stmt = view.create_statement
        assert "security_invoker=true" in stmt.lower()

    def test_view_with_dependencies(self):
        """Test view with dependencies property."""
        view = View.from_options(
            name="dependent_view",
            query="SELECT * FROM table1 JOIN table2",
            dialect="postgresql",
            options=ViewOptions(dependencies=["table1", "table2"]),
        )

        assert view.dependencies == ["table1", "table2"]

    def test_view_security_serialization(self):
        """Test view security properties in to_dict and from_dict."""
        view = View.from_options(
            name="secure_view",
            query="SELECT * FROM data",
            dialect="postgresql",
            options=ViewOptions(
                postgres=PostgresViewOptions(security_definer=True, security_invoker=False),
                dependencies=["table1"],
            ),
        )
        data = view.to_dict()

        assert data.get("security_definer") is True
        assert data.get("security_invoker") is False
        assert data.get("dependencies") == ["table1"]

        restored = View.from_dict(data)
        assert restored.security_definer is True
        assert restored.security_invoker is False
        assert restored.dependencies == ["table1"]
