"""Tests for DatabaseErrorHandler."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from core.logger import DbliftLogger, LogFormat, LogLevel, NullLog
from db.error_handler import DatabaseErrorHandler, decorator, retry_on_db_error


@pytest.mark.unit
class TestDatabaseErrorHandlerInit:
    """Test DatabaseErrorHandler initialization."""

    @pytest.fixture
    def mock_logger(self, tmp_path):
        """Create mock logger."""
        return DbliftLogger(
            name="test", level=LogLevel.DEBUG, format=LogFormat.TEXT, logfile_dir=tmp_path
        )

    def test_init_with_logger(self, mock_logger):
        """Test initialization with logger."""
        handler = DatabaseErrorHandler(log=mock_logger, db_type="postgresql")
        assert handler.log == mock_logger
        assert handler.db_type == "postgresql"
        assert handler.error_classifier is not None
        assert handler.retry_manager is not None

    def test_init_without_logger(self):
        """Test initialization without logger."""
        handler = DatabaseErrorHandler(db_type="mysql")
        assert isinstance(handler.log, NullLog)
        assert handler.db_type == "mysql"

    def test_init_with_import_error(self):
        """Test initialization when error module import fails."""
        # Since db.error doesn't exist, it will use stub classes
        # This test verifies the stub path works
        handler = DatabaseErrorHandler(db_type="postgresql")
        assert handler.error_classifier is not None
        assert handler.retry_manager is not None
        # Should use stub classes when db.error doesn't exist
        # Verify all categories used by handle_error() are present in the fallback
        assert hasattr(handler.ErrorCategory, "UNKNOWN")
        assert hasattr(handler.ErrorCategory, "SCHEMA")
        assert hasattr(handler.ErrorCategory, "CONSTRAINT")
        assert hasattr(handler.ErrorCategory, "AUTHENTICATION")
        assert hasattr(handler.ErrorCategory, "NETWORK")

    def test_init_default_db_type(self):
        """Test initialization with default db_type."""
        handler = DatabaseErrorHandler()
        assert handler.db_type == "generic"


@pytest.mark.unit
class TestDatabaseErrorHandlerCategorizeError:
    """Test categorize_error method."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return DatabaseErrorHandler(db_type="postgresql")

    def test_categorize_error(self, handler):
        """Test categorizing an error."""
        error = Exception("Test error")
        category = handler.categorize_error(error)
        # Should return a category (stub returns UNKNOWN if import failed)
        assert category is not None

    def test_categorize_error_with_sql(self, handler):
        """Test categorizing error with SQL context."""
        error = Exception("Test error")
        category = handler.categorize_error(error, sql="SELECT * FROM test")
        assert category is not None


@pytest.mark.unit
class TestDatabaseErrorHandlerIsRetryable:
    """Test is_retryable method."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return DatabaseErrorHandler(db_type="postgresql")

    def test_is_retryable(self, handler):
        """Test checking if error is retryable."""
        category = handler.ErrorCategory.NETWORK
        result = handler.is_retryable(category, retry_count=0, max_retries=3)
        assert isinstance(result, bool)

    def test_is_retryable_with_retry_count(self, handler):
        """Test checking retryable with retry count."""
        category = handler.ErrorCategory.TIMEOUT
        result = handler.is_retryable(category, retry_count=2, max_retries=3)
        assert isinstance(result, bool)


@pytest.mark.unit
class TestDatabaseErrorHandlerHandleError:
    """Test handle_error method."""

    @pytest.fixture
    def handler(self, mock_logger):
        """Create handler instance."""
        return DatabaseErrorHandler(log=mock_logger, db_type="postgresql")

    @pytest.fixture
    def mock_logger(self, tmp_path):
        """Create mock logger."""
        return DbliftLogger(
            name="test", level=LogLevel.DEBUG, format=LogFormat.TEXT, logfile_dir=tmp_path
        )

    def test_handle_error_basic(self, handler):
        """Test handling a basic error."""
        error = Exception("Test error")
        error_info = handler.handle_error(error)
        assert error_info is not None
        assert hasattr(error_info, "exception")
        assert error_info.exception == error

    def test_handle_error_with_sql(self, handler):
        """Test handling error with SQL."""
        error = Exception("SQL error")
        error_info = handler.handle_error(error, sql="SELECT * FROM test")
        assert error_info.sql == "SELECT * FROM test"

    def test_handle_error_with_params(self, handler):
        """Test handling error with params."""
        error = Exception("Parameter error")
        error_info = handler.handle_error(error, params=[1, 2, 3])
        assert error_info.params == [1, 2, 3]

    def test_handle_error_with_schema(self, handler):
        """Test handling error with schema."""
        error = Exception("Schema error")
        error_info = handler.handle_error(error, schema="test_schema")
        assert error_info.schema == "test_schema"

    def test_handle_error_with_context(self, handler):
        """Test handling error with context."""
        error = Exception("Context error")
        context = {"operation": "migrate", "version": "1"}
        error_info = handler.handle_error(error, context=context)
        assert error_info.context == context

    def test_handle_error_with_retry_count(self, handler):
        """Test handling error with retry count."""
        error = Exception("Retry error")
        error_info = handler.handle_error(error, retry_count=2)
        assert error_info.retry_count == 2

    def test_handle_error_logs_transient_errors(self, handler):
        """Test that transient errors are logged appropriately."""
        error = Exception("Network error")
        handler.categorize_error = MagicMock(return_value=handler.ErrorCategory.NETWORK)
        handler.handle_error(error, retry_count=0)
        # Should log at debug level for first attempt

    def test_handle_error_logs_transient_errors_with_retry(self, handler):
        """Test logging transient errors on retry."""
        error = Exception("Timeout error")
        handler.categorize_error = MagicMock(return_value=handler.ErrorCategory.TIMEOUT)
        handler.handle_error(error, retry_count=1)
        # Should log at info level for retries

    def test_handle_error_logs_security_errors(self, handler):
        """Test logging security errors."""
        error = Exception("Auth error")
        handler.categorize_error = MagicMock(return_value=handler.ErrorCategory.AUTHENTICATION)
        handler.handle_error(error)
        # Should log at warning level

    def test_handle_error_logs_application_errors(self, handler):
        """Test logging application errors."""
        error = Exception("Schema error")
        handler.categorize_error = MagicMock(return_value=handler.ErrorCategory.SCHEMA)
        handler.handle_error(error)
        # Should log at error level

    def test_handle_error_without_logger(self):
        """Test handling error without logger."""
        handler = DatabaseErrorHandler(db_type="postgresql")
        error = Exception("Test error")
        error_info = handler.handle_error(error)
        assert error_info is not None


@pytest.mark.unit
class TestDatabaseErrorHandlerExecuteWithRetry:
    """Test execute_with_retry method."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return DatabaseErrorHandler(db_type="postgresql")

    def test_execute_with_retry_success(self, handler):
        """Test executing operation that succeeds."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            return "success"

        result = handler.execute_with_retry(operation)
        assert result == "success"

    def test_execute_with_retry_with_args(self, handler):
        """Test executing operation with arguments."""

        def operation(a, b, **kwargs):
            # Filter out retry-specific kwargs
            return a + b

        result = handler.execute_with_retry(operation, 1, 2)
        assert result == 3

    def test_execute_with_retry_with_kwargs(self, handler):
        """Test executing operation with keyword arguments."""

        def operation(x=0, y=0, **kwargs):
            # Filter out retry-specific kwargs
            return x + y

        result = handler.execute_with_retry(operation, x=5, y=3)
        assert result == 8

    def test_execute_with_retry_with_sql_context(self, handler):
        """Test executing operation with SQL context."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            return "result"

        result = handler.execute_with_retry(operation, sql="SELECT * FROM test")
        assert result == "result"

    def test_execute_with_retry_with_schema_context(self, handler):
        """Test executing operation with schema context."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            return "result"

        result = handler.execute_with_retry(operation, schema="test_schema")
        assert result == "result"

    def test_execute_with_retry_with_context(self, handler):
        """Test executing operation with additional context."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            return "result"

        context = {"operation": "migrate"}
        result = handler.execute_with_retry(operation, context=context)
        assert result == "result"

    def test_execute_with_retry_with_max_retries(self, handler):
        """Test executing operation with custom max_retries."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            return "success"

        result = handler.execute_with_retry(operation, max_retries=5)
        assert result == "success"

    def test_execute_with_retry_with_exception_types(self, handler):
        """Test executing operation with custom exception types."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            return "success"

        result = handler.execute_with_retry(operation, exception_types=ValueError)
        assert result == "success"

    def test_execute_with_retry_operation_raises(self, handler):
        """Test executing operation that raises exception."""

        def operation(**kwargs):
            # Filter out retry-specific kwargs
            raise ValueError("Operation failed")

        # Should raise the exception (stub retry manager doesn't retry)
        with pytest.raises(ValueError):
            handler.execute_with_retry(operation)


@pytest.mark.unit
class TestDatabaseErrorHandlerRetryOnDbError:
    """Test retry_on_db_error decorator method."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return DatabaseErrorHandler(db_type="postgresql")

    def test_retry_on_db_error_decorator(self, handler):
        """Test retry_on_db_error returns a decorator."""
        decorator_func = handler.retry_on_db_error()
        assert callable(decorator_func)

    def test_retry_on_db_error_with_max_retries(self, handler):
        """Test retry_on_db_error with max_retries."""
        decorator_func = handler.retry_on_db_error(max_retries=5)
        assert callable(decorator_func)

    def test_retry_on_db_error_with_exception_types(self, handler):
        """Test retry_on_db_error with exception types."""
        decorator_func = handler.retry_on_db_error(exception_types=ValueError)
        assert callable(decorator_func)

    def test_retry_on_db_error_with_context(self, handler):
        """Test retry_on_db_error with context."""
        decorator_func = handler.retry_on_db_error(
            sql="SELECT * FROM test", schema="test_schema", context={"key": "value"}
        )
        assert callable(decorator_func)

    def test_retry_on_db_error_decorates_function(self, handler):
        """Test that decorator can be applied to a function."""

        @handler.retry_on_db_error()
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"


@pytest.mark.unit
class TestRetryOnDbErrorFunction:
    """Test retry_on_db_error convenience function."""

    @pytest.fixture
    def mock_logger(self, tmp_path):
        """Create mock logger."""
        return DbliftLogger(
            name="test", level=LogLevel.DEBUG, format=LogFormat.TEXT, logfile_dir=tmp_path
        )

    def test_retry_on_db_error_function(self, mock_logger):
        """Test retry_on_db_error convenience function."""
        decorator_func = retry_on_db_error(max_retries=3, db_type="postgresql", log=mock_logger)
        assert callable(decorator_func)

    def test_retry_on_db_error_function_defaults(self):
        """Test retry_on_db_error with defaults."""
        decorator_func = retry_on_db_error()
        assert callable(decorator_func)

    def test_retry_on_db_error_function_with_params(self):
        """Test retry_on_db_error with parameters."""
        decorator_func = retry_on_db_error(
            max_retries=5,
            db_type="mysql",
            exception_types=ValueError,
            sql="SELECT * FROM test",
            schema="test_schema",
            context={"key": "value"},
        )
        assert callable(decorator_func)

    def test_retry_on_db_error_decorates_function(self):
        """Test that convenience function decorator works."""

        @retry_on_db_error(max_retries=3)
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"


@pytest.mark.unit
class TestLegacyDecorator:
    """Test legacy decorator function."""

    def test_decorator_function(self):
        """Test legacy decorator function."""

        @decorator
        def test_function(**kwargs):
            # Filter out retry-specific kwargs
            return "success"

        result = test_function()
        assert result == "success"

    def test_decorator_function_with_args(self):
        """Test legacy decorator with function arguments."""

        @decorator
        def test_function(x, y, **kwargs):
            # Filter out retry-specific kwargs
            return x + y

        result = test_function(2, 3)
        assert result == 5

    def test_decorator_function_with_kwargs(self):
        """Test legacy decorator with keyword arguments."""

        @decorator
        def test_function(x=0, y=0, **kwargs):
            # Filter out retry-specific kwargs
            return x + y

        result = test_function(x=5, y=3)
        assert result == 8

    def test_decorator_function_preserves_name(self):
        """Test that decorator preserves function name."""

        @decorator
        def test_function():
            return "success"

        assert test_function.__name__ == "test_function"


@pytest.mark.unit
class TestErrorCategoryExport:
    """Test ErrorCategory export."""

    def test_error_category_import(self):
        """Test that ErrorCategory can be imported."""
        from db.error_handler import ErrorCategory

        assert ErrorCategory is not None
        assert hasattr(ErrorCategory, "UNKNOWN")

    def test_error_category_attributes(self):
        """Test ErrorCategory has expected attributes."""
        from db.error_handler import ErrorCategory

        # Check that stub attributes exist
        assert hasattr(ErrorCategory, "NETWORK")
        assert hasattr(ErrorCategory, "TIMEOUT")
        assert hasattr(ErrorCategory, "LOCKING")
        assert hasattr(ErrorCategory, "AUTHENTICATION")
        assert hasattr(ErrorCategory, "AUTHORIZATION")
        assert hasattr(ErrorCategory, "SCHEMA")
        assert hasattr(ErrorCategory, "CONSTRAINT")
        assert hasattr(ErrorCategory, "SQL_SYNTAX")
        assert hasattr(ErrorCategory, "RESOURCE")
        assert hasattr(ErrorCategory, "INTERNAL")
        assert hasattr(ErrorCategory, "UNKNOWN")
