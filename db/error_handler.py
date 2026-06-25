"""
Database error handler implementation.

This handler uses modular components to provide comprehensive error handling
for database operations with classification, retry logic, and detailed reporting.
"""

import functools
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from core.logger import Log, NullLog


class _ErrorCategoryFallback:
    """Fallback ErrorCategory stub used when the .error module is unavailable.

    Contains the categories referenced by handle_error() — PERMISSION is intentionally
    absent as it is not used by any production code path in this module.
    """

    NETWORK = "network"
    TIMEOUT = "timeout"
    LOCKING = "locking"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SCHEMA = "schema"
    CONSTRAINT = "constraint"
    SQL_SYNTAX = "sql_syntax"
    RESOURCE = "resource"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class DatabaseErrorHandler:
    """Handler for database errors with retry logic and error classification."""

    def __init__(self, log: Optional[Log] = None, db_type: str = "generic"):
        """Initialize the database error handler.

        Args:
            log: Optional logger instance
            db_type: Database type for specific error patterns
        """
        self.log = log if log is not None else NullLog()
        self.db_type = db_type

        # Lazy import to avoid import errors when error handling is not used
        try:
            from .error import (
                DatabaseErrorClassifier,
                DatabaseErrorInfo,
                ErrorCategory,
                RetryManager,
            )

            self.ErrorCategory = ErrorCategory
            self.DatabaseErrorInfo = DatabaseErrorInfo
        except ImportError:
            # Create minimal stubs if error module doesn't exist
            class _DatabaseErrorInfoStub:
                def __init__(self, **kwargs: Any) -> None:
                    for k, v in kwargs.items():
                        setattr(self, k, v)

                def __str__(self) -> str:
                    return str(self.exception) if hasattr(self, "exception") else "Database error"

            class _DatabaseErrorClassifierStub:
                def __init__(self, db_type: str, log: Optional[Log]) -> None:
                    pass

                def categorize_error(self, error: Exception, sql: Optional[str] = None) -> Any:
                    return _ErrorCategoryFallback.UNKNOWN

                def is_retryable(
                    self, category: Any, retry_count: int = 0, max_retries: int = 3
                ) -> bool:
                    return False

            class _RetryManagerStub:
                def __init__(
                    self, error_classifier: Any, log: Optional[Log], **kwargs: Any
                ) -> None:
                    pass

                def execute_with_retry(
                    self, operation: Callable[..., Any], *args: Any, **kwargs: Any
                ) -> Any:
                    return operation(*args, **kwargs)

                def retry_on_db_error(self, **kwargs: Any) -> Callable[..., Any]:
                    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                        return func

                    return decorator

            DatabaseErrorClassifier = _DatabaseErrorClassifierStub  # type: ignore[misc,assignment]
            RetryManager = _RetryManagerStub  # type: ignore[misc,assignment]
            self.ErrorCategory = _ErrorCategoryFallback  # type: ignore[assignment]
            self.DatabaseErrorInfo = _DatabaseErrorInfoStub  # type: ignore[assignment]
            # Store references for use in methods
            self._DatabaseErrorClassifier = DatabaseErrorClassifier
            self._RetryManager = RetryManager
        else:
            # Store references for use in methods
            self._DatabaseErrorClassifier = DatabaseErrorClassifier
            self._RetryManager = RetryManager

        # Initialize modular components
        self.error_classifier = self._DatabaseErrorClassifier(db_type, log)
        self.retry_manager = self._RetryManager(self.error_classifier, log)

    def categorize_error(self, error: Exception, sql: Optional[str] = None) -> Any:
        """Categorize a database error based on the exception and context.

        Args:
            error: The exception to categorize
            sql: Optional SQL statement that caused the error

        Returns:
            ErrorCategory: The category of the error
        """
        return self.error_classifier.categorize_error(error, sql)

    def is_retryable(self, category: Any, retry_count: int = 0, max_retries: int = 3) -> bool:
        """Determine if an error should be retried based on its category.

        Args:
            category: Error category
            retry_count: Current retry count
            max_retries: Maximum number of retries allowed

        Returns:
            bool: True if the error should be retried
        """
        result = self.error_classifier.is_retryable(category, retry_count, max_retries)
        return bool(result)

    def handle_error(
        self,
        error: Exception,
        sql: Optional[str] = None,
        params: Optional[List[Any]] = None,
        schema: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Any:
        """Handle a database error by categorizing it and creating detailed error info.

        Args:
            error: The exception that was raised
            sql: SQL statement that caused the error (if applicable)
            params: Parameters for the SQL statement (if applicable)
            schema: Database schema context (if applicable)
            context: Additional context information
            retry_count: How many retries have been attempted

        Returns:
            DatabaseErrorInfo: Detailed error information
        """
        # Categorize the error
        category = self.categorize_error(error, sql)

        # Create detailed error info
        error_info = self.DatabaseErrorInfo(
            exception=error,
            sql=sql,
            params=params,
            schema=schema,
            category=category,
            retry_count=retry_count,
            context=context or {},
        )

        # Log the error based on its severity
        ErrorCategory = self.ErrorCategory
        if category in (ErrorCategory.NETWORK, ErrorCategory.TIMEOUT, ErrorCategory.LOCKING):
            # These are often transient, log at debug/info level
            if retry_count > 0:
                self.log.info(f"Transient database error (retry {retry_count}): {error_info}")
            else:
                self.log.debug(f"Transient database error: {error_info}")
        elif category in (ErrorCategory.AUTHENTICATION, ErrorCategory.AUTHORIZATION):
            # These are security-related, log at warning level
            self.log.warning(f"Database security error: {error_info}")
        elif category in (
            ErrorCategory.SCHEMA,
            ErrorCategory.CONSTRAINT,
            ErrorCategory.SQL_SYNTAX,
        ):
            # These are likely application/configuration issues
            self.log.error(f"Database application error: {error_info}")
        else:
            # Other errors (resource, internal, unknown)
            self.log.error(f"Database error: {error_info}")

        return error_info

    def execute_with_retry(
        self,
        operation: Callable[..., Any],
        *args: Any,
        sql: Optional[str] = None,
        schema: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
        exception_types: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
        **kwargs: Any,
    ) -> Any:
        """Execute an operation with retry logic.

        Args:
            operation: The operation to execute
            *args: Positional arguments for the operation
            sql: SQL statement context (for error reporting)
            schema: Schema context (for error reporting)
            context: Additional context for error reporting
            max_retries: Override default max retries
            exception_types: Exception types to catch and potentially retry
            **kwargs: Keyword arguments for the operation

        Returns:
            The result of the operation

        Raises:
            The last exception if all retries are exhausted
        """
        # Update retry manager max_retries if specified
        if max_retries is not None:
            # Create temporary retry manager with custom max_retries
            # Use getattr with defaults to handle stub classes that may not have these attributes
            base_delay = getattr(self.retry_manager, "base_delay", 1.0)
            max_delay = getattr(self.retry_manager, "max_delay", 60.0)
            backoff_multiplier = getattr(self.retry_manager, "backoff_multiplier", 2.0)
            jitter = getattr(self.retry_manager, "jitter", 0.2)

            temp_retry_manager = self._RetryManager(
                error_classifier=self.error_classifier,
                log=self.log,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_multiplier=backoff_multiplier,
                jitter=jitter,
            )
            return temp_retry_manager.execute_with_retry(
                operation,
                *args,
                sql=sql,
                schema=schema,
                context=context,
                exception_types=exception_types,
                **kwargs,
            )
        else:
            return self.retry_manager.execute_with_retry(
                operation,
                *args,
                sql=sql,
                schema=schema,
                context=context,
                exception_types=exception_types,
                **kwargs,
            )

    def retry_on_db_error(
        self,
        max_retries: Optional[int] = None,
        exception_types: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
        sql: Optional[str] = None,
        schema: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Callable[..., Any]:
        """Decorator to automatically retry database operations on error.

        Args:
            max_retries: Override default max retries
            exception_types: Exception types to catch and retry
            sql: SQL statement context
            schema: Schema context
            context: Additional context

        Returns:
            Decorator function
        """
        return self.retry_manager.retry_on_db_error(
            max_retries=max_retries,
            exception_types=exception_types,
            sql=sql,
            schema=schema,
            context=context,
        )


# Convenience function to create a retry decorator
def retry_on_db_error(
    max_retries: int = 3,
    db_type: str = "generic",
    exception_types: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    sql: Optional[str] = None,
    schema: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    log: Optional[Log] = None,
) -> Callable[..., Any]:
    """Create a retry decorator for database operations.

    This is a convenience function that creates a DatabaseErrorHandler and
    returns its retry decorator.

    Args:
        max_retries: Maximum number of retry attempts
        db_type: Database type for specific error patterns
        exception_types: Exception types to catch and retry
        sql: SQL statement context
        schema: Schema context
        context: Additional context
        log: Optional logger

    Returns:
        Decorator function
    """
    handler = DatabaseErrorHandler(log=log, db_type=db_type)
    return handler.retry_on_db_error(
        max_retries=max_retries,
        exception_types=exception_types,
        sql=sql,
        schema=schema,
        context=context,
    )


def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
    """Legacy decorator function for backward compatibility."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Create a default error handler and execute with retry
        handler = DatabaseErrorHandler()
        return handler.execute_with_retry(func, *args, **kwargs)

    return wrapper


# Export ErrorCategory for backward compatibility with tests
# Try to import from .error, otherwise use the stub class
try:
    from .error import ErrorCategory
except ImportError:
    ErrorCategory = _ErrorCategoryFallback  # type: ignore[misc,assignment]
