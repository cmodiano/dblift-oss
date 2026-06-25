"""Unit tests for core.state.sql_script_formatter module."""

from unittest.mock import Mock

import pytest

from core.state.sql_script_formatter import SqlScriptFormatter


@pytest.mark.unit
class TestSqlScriptFormatter:
    """Test SqlScriptFormatter class."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        formatter = SqlScriptFormatter()
        assert formatter.include_comments is True
        assert formatter.include_checks is True

    def test_init_with_parameters(self):
        """Test initialization with custom parameters."""
        formatter = SqlScriptFormatter(include_comments=False, include_checks=False)
        assert formatter.include_comments is False
        assert formatter.include_checks is False

    def test_format_script_empty_statements(self):
        """Test formatting script with empty statements list."""
        formatter = SqlScriptFormatter()
        result = formatter.format_script([])
        assert "-- Generated:" in result
        assert "-- Total statements: 0" in result

    def test_format_script_with_title(self):
        """Test formatting script with title."""
        formatter = SqlScriptFormatter()
        result = formatter.format_script([], title="Test Script")
        assert "-- Test Script" in result
        assert "===" in result

    def test_format_script_with_description(self):
        """Test formatting script with description."""
        formatter = SqlScriptFormatter()
        result = formatter.format_script([], description="Test description")
        assert "-- Test description" in result

    def test_format_script_with_title_and_description(self):
        """Test formatting script with title and description."""
        formatter = SqlScriptFormatter()
        result = formatter.format_script([], title="Test Script", description="Test description")
        assert "-- Test Script" in result
        assert "-- Test description" in result

    def test_format_script_create_statements(self):
        """Test formatting script with CREATE statements."""
        formatter = SqlScriptFormatter()
        stmt = Mock()
        stmt.statement_type = "CREATE"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "CREATE TABLE test_table (id INT);"
        stmt.pre_check = None
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter.format_script([stmt])
        assert "-- CREATE OBJECTS" in result
        assert "CREATE TABLE test_table" in result

    def test_format_script_alter_statements(self):
        """Test formatting script with ALTER statements."""
        formatter = SqlScriptFormatter()
        stmt = Mock()
        stmt.statement_type = "ALTER"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "ALTER TABLE test_table ADD COLUMN name VARCHAR(50);"
        stmt.pre_check = None
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter.format_script([stmt])
        assert "-- ALTER OBJECTS" in result
        assert "ALTER TABLE test_table" in result

    def test_format_script_drop_statements(self):
        """Test formatting script with DROP statements."""
        formatter = SqlScriptFormatter()
        stmt = Mock()
        stmt.statement_type = "DROP"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "DROP TABLE test_table;"
        stmt.pre_check = None
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter.format_script([stmt])
        assert "-- DROP OBJECTS" in result
        assert "WARNING:" in result
        assert "DROP TABLE test_table" in result

    def test_format_script_mixed_statements(self):
        """Test formatting script with mixed statement types."""
        formatter = SqlScriptFormatter()

        create_stmt = Mock()
        create_stmt.statement_type = "CREATE"
        create_stmt.object_type = "TABLE"
        create_stmt.object_name = "table1"
        create_stmt.sql = "CREATE TABLE table1;"
        create_stmt.pre_check = None
        create_stmt.error_if_check_fails = False
        create_stmt.error_message = None

        alter_stmt = Mock()
        alter_stmt.statement_type = "ALTER"
        alter_stmt.object_type = "TABLE"
        alter_stmt.object_name = "table1"
        alter_stmt.sql = "ALTER TABLE table1 ADD COLUMN id INT;"
        alter_stmt.pre_check = None
        alter_stmt.error_if_check_fails = False
        alter_stmt.error_message = None

        drop_stmt = Mock()
        drop_stmt.statement_type = "DROP"
        drop_stmt.object_type = "TABLE"
        drop_stmt.object_name = "table2"
        drop_stmt.sql = "DROP TABLE table2;"
        drop_stmt.pre_check = None
        drop_stmt.error_if_check_fails = False
        drop_stmt.error_message = None

        result = formatter.format_script([create_stmt, alter_stmt, drop_stmt])
        assert "-- CREATE OBJECTS" in result
        assert "-- ALTER OBJECTS" in result
        assert "-- DROP OBJECTS" in result

    def test_format_statement_with_comments(self):
        """Test formatting statement with comments enabled."""
        formatter = SqlScriptFormatter(include_comments=True)
        stmt = Mock()
        stmt.statement_type = "CREATE"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "CREATE TABLE test_table;"
        stmt.pre_check = None
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter._format_statement(stmt)
        assert any("-- CREATE TABLE: test_table" in line for line in result)
        assert "CREATE TABLE test_table;" in result

    def test_format_statement_without_comments(self):
        """Test formatting statement with comments disabled."""
        formatter = SqlScriptFormatter(include_comments=False)
        stmt = Mock()
        stmt.statement_type = "CREATE"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "CREATE TABLE test_table;"
        stmt.pre_check = None
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter._format_statement(stmt)
        assert not any("-- CREATE TABLE: test_table" in line for line in result)
        assert "CREATE TABLE test_table;" in result

    def test_format_statement_with_pre_check(self):
        """Test formatting statement with pre-execution check."""
        formatter = SqlScriptFormatter(include_checks=True)
        stmt = Mock()
        stmt.statement_type = "CREATE"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "CREATE TABLE test_table;"
        stmt.pre_check = (
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'test_table'"
        )
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter._format_statement(stmt)
        assert any("-- Pre-execution check:" in line for line in result)
        assert any("SELECT COUNT(*)" in line for line in result)

    def test_format_statement_with_pre_check_error(self):
        """Test formatting statement with pre-check that errors on failure."""
        formatter = SqlScriptFormatter(include_checks=True)
        stmt = Mock()
        stmt.statement_type = "CREATE"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "CREATE TABLE test_table;"
        stmt.pre_check = "SELECT COUNT(*) FROM test_table"
        stmt.error_if_check_fails = True
        stmt.error_message = "Table already exists"

        result = formatter._format_statement(stmt)
        assert any("-- Pre-execution check:" in line for line in result)
        assert any("ERROR if check fails: Table already exists" in line for line in result)

    def test_format_statement_without_checks(self):
        """Test formatting statement with checks disabled."""
        formatter = SqlScriptFormatter(include_checks=False)
        stmt = Mock()
        stmt.statement_type = "CREATE"
        stmt.object_type = "TABLE"
        stmt.object_name = "test_table"
        stmt.sql = "CREATE TABLE test_table;"
        stmt.pre_check = "SELECT COUNT(*) FROM test_table"
        stmt.error_if_check_fails = False
        stmt.error_message = None

        result = formatter._format_statement(stmt)
        assert not any("-- Pre-execution check:" in line for line in result)

    def test_format_statements_simple(self):
        """Test format_statements_simple method."""
        formatter = SqlScriptFormatter()
        stmt1 = Mock()
        stmt1.sql = "CREATE TABLE table1;"
        stmt2 = Mock()
        stmt2.sql = "CREATE TABLE table2;"

        result = formatter.format_statements_simple([stmt1, stmt2])
        assert "CREATE TABLE table1;" in result
        assert "CREATE TABLE table2;" in result
        assert "\n\n" in result  # Should have double newline separator

    def test_format_statements_simple_empty(self):
        """Test format_statements_simple with empty list."""
        formatter = SqlScriptFormatter()
        result = formatter.format_statements_simple([])
        assert result == ""

    def test_format_statements_simple_single(self):
        """Test format_statements_simple with single statement."""
        formatter = SqlScriptFormatter()
        stmt = Mock()
        stmt.sql = "CREATE TABLE test_table;"

        result = formatter.format_statements_simple([stmt])
        assert result == "CREATE TABLE test_table;"
