"""Comprehensive tests for db.plugins.base_query_executor.BaseQueryExecutor."""

from unittest.mock import MagicMock

import pytest

from core.logger import NullLog
from db.plugins.base_query_executor import BaseQueryExecutor


class ConcreteQueryExecutor(BaseQueryExecutor):
    """Concrete implementation of BaseQueryExecutor for testing."""

    def execute_statement(self, connection, sql: str, params=None, return_generated_keys=False):
        return 1

    def execute_query(self, connection, sql: str, params=None):
        return []

    def table_exists(self, connection, schema: str, table_name: str):
        return False

    def get_schema_qualified_name(self, schema: str, object_name: str):
        return f"{schema}.{object_name}"


@pytest.mark.unit
class TestBaseQueryExecutor:
    """Test suite for BaseQueryExecutor base class."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Create a mock connection manager."""
        return MagicMock()

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return MagicMock()

    @pytest.fixture
    def query_executor(self, mock_connection_manager, mock_logger):
        """Create a concrete query executor instance."""
        return ConcreteQueryExecutor(mock_connection_manager, mock_logger)

    @pytest.fixture
    def mock_connection(self):
        """Create a mock native connection."""
        connection = MagicMock()
        connection.isClosed.return_value = False
        return connection

    def test_init_stores_dependencies(self, mock_connection_manager, mock_logger):
        """Test __init__ stores dependencies."""
        executor = ConcreteQueryExecutor(mock_connection_manager, mock_logger)

        assert executor.connection_manager == mock_connection_manager
        assert executor.log == mock_logger

    def test_init_without_logger(self, mock_connection_manager):
        """Test __init__ works without logger."""
        executor = ConcreteQueryExecutor(mock_connection_manager, None)

        assert isinstance(executor.log, NullLog)

    def test_no_log_wrapper_methods(self):
        """Verify log wrappers have been removed (story 18-4)."""
        wrappers = ["_log_debug", "_log_info", "_log_error", "_log_warning"]
        for name in wrappers:
            assert (
                name not in BaseQueryExecutor.__dict__
            ), f"Log wrapper {name!r} must be removed from BaseQueryExecutor (story 18-4)"

    def test_truncate_sql_for_logging_returns_full_sql_when_short(self, query_executor):
        """Test _truncate_sql_for_logging() returns full SQL when short."""
        sql = "SELECT * FROM users"

        result = query_executor._truncate_sql_for_logging(sql)

        assert result == sql

    def test_truncate_sql_for_logging_truncates_long_sql(self, query_executor):
        """Test _truncate_sql_for_logging() truncates long SQL."""
        sql = "SELECT " + ", ".join([f"col{i}" for i in range(100)])
        max_length = 50

        result = query_executor._truncate_sql_for_logging(sql, max_length=max_length)

        # max_length + len("...") = 53
        assert len(result) <= max_length + len("...")
        assert result.endswith("...")

    def test_truncate_sql_for_logging_delegates_to_module_level(self, query_executor):
        """AC#2 structural: _truncate_sql_for_logging() must delegate to truncate_sql_for_logging() (story 18-12)."""
        import inspect

        src = inspect.getsource(query_executor._truncate_sql_for_logging)
        assert (
            "truncate_sql_for_logging" in src
        ), "_truncate_sql_for_logging must delegate to module-level truncate_sql_for_logging()"

    def test_validate_connection_raises_on_none(self, query_executor):
        """Test _validate_connection() raises on None."""
        with pytest.raises(RuntimeError, match="No database connection provided"):
            query_executor._validate_connection(None)

    def test_validate_connection_raises_on_closed(self, query_executor):
        """Test _validate_connection() raises on closed connection."""
        connection = MagicMock()
        connection.isClosed.return_value = True

        with pytest.raises(RuntimeError, match="Database connection is closed"):
            query_executor._validate_connection(connection)

    def test_validate_connection_passes_on_open_connection(self, query_executor, mock_connection):
        """Test _validate_connection() passes on open connection."""
        # Should not raise exception
        query_executor._validate_connection(mock_connection)

    def test_format_identifier_returns_as_is(self, query_executor):
        """Test _format_identifier() returns identifier as-is by default."""
        assert query_executor._format_identifier("users") == "users"
        assert query_executor._format_identifier("MyTable") == "MyTable"

    def test_get_parameter_placeholder_returns_question_mark(self, query_executor):
        """Test _get_parameter_placeholder() returns '?' by default."""
        assert query_executor._get_parameter_placeholder() == "?"

    def test_build_parameter_placeholders_creates_placeholders(self, query_executor):
        """Test _build_parameter_placeholders() creates comma-separated placeholders."""
        result = query_executor._build_parameter_placeholders(3)

        assert result == "?, ?, ?"

        result = query_executor._build_parameter_placeholders(1)
        assert result == "?"

        result = query_executor._build_parameter_placeholders(0)
        assert result == ""

    def test_is_connection_error_detects_connection_errors(self, query_executor):
        """Test _is_connection_error() detects connection-related errors."""
        assert query_executor._is_connection_error(Exception("Connection timeout")) is True
        assert query_executor._is_connection_error(Exception("Network unreachable")) is True
        assert query_executor._is_connection_error(Exception("Connection closed")) is True
        assert query_executor._is_connection_error(Exception("Connection broken")) is True
        assert query_executor._is_connection_error(Exception("Connection refused")) is True

    def test_is_connection_error_returns_false_for_other_errors(self, query_executor):
        """Test _is_connection_error() returns False for non-connection errors."""
        assert query_executor._is_connection_error(Exception("Syntax error")) is False
        assert query_executor._is_connection_error(Exception("Table not found")) is False
        assert query_executor._is_connection_error(ValueError("Invalid value")) is False
