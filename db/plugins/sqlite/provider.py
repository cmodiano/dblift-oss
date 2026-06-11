"""
SQLite provider implementation with modular components.

This provider uses Python's native sqlite3 module.
"""

import sqlite3
from typing import Any, Dict, List, Optional

from config import DbliftConfig
from core.logger import Log
from core.migration.clean_summary import CleanExecutionSummary
from db.base_provider import NativeProvider
from db.plugins.sqlite.sqlite import (
    SQLiteConnectionManager,
    SQLiteHistoryManager,
    SQLiteLockingManager,
    SQLiteQueryExecutor,
    SQLiteSchemaOperations,
)


class SQLiteProvider(NativeProvider):
    """SQLite provider implementation using Python's native sqlite3 module."""

    canonical_dialect_key = "sqlite"

    # Keep the lock-table name available to internal-table filters.
    MIGRATION_LOCK_TABLE = "dblift_migration_lock"

    def __init__(self, config: DbliftConfig, log: Optional[Log] = None) -> None:
        """Initialize SQLite provider with modular components.

        Args:
            config: Application configuration
            log: Optional logger
        """
        super().__init__(config, log)

        # Initialize modular components
        self.connection_manager = SQLiteConnectionManager(config, log)
        self.query_executor = SQLiteQueryExecutor(self.connection_manager, log)
        self.locking_manager = SQLiteLockingManager(self.query_executor, log)
        self.schema_operations = SQLiteSchemaOperations(self.query_executor, log)
        self.history_manager = SQLiteHistoryManager(
            self.query_executor, self.schema_operations, config, log
        )

        # Store connection reference
        self.connection: Optional[sqlite3.Connection] = None

    def create_connection(self) -> sqlite3.Connection:
        """Create a connection to SQLite database.

        Returns:
            sqlite3.Connection: SQLite connection object
        """
        connection = self.connection_manager.create_connection()
        self.connection = connection

        # Start in autocommit mode (SQLite default with isolation_level=None)
        # For transaction control, we'll use explicit BEGIN/COMMIT/ROLLBACK

        return connection

    def _ensure_connection(self) -> None:
        """Ensure we have an active database connection."""
        if self.connection is None:
            self.create_connection()
        else:
            # Verify connection is still valid
            try:
                self.connection.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                # Connection is closed, create a new one
                self.create_connection()

    def _get_connection(self) -> sqlite3.Connection:
        """Get the connection, ensuring it exists."""
        self._ensure_connection()
        if self.connection is None:
            raise RuntimeError("Connection is None after _ensure_connection()")
        return self.connection

    def execute_statement(
        self, sql: str, schema: Optional[str] = None, params: Optional[List[Any]] = None
    ) -> int:
        """Execute a SQL statement and return affected rows.

        Args:
            sql: SQL statement to execute
            schema: Schema name (ignored for SQLite)
            params: Optional parameters

        Returns:
            int: Number of affected rows
        """
        connection = self._get_connection()
        return self.query_executor.execute_statement(connection, sql, params)

    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results.

        Args:
            sql: SQL query to execute
            params: Optional parameters

        Returns:
            List[Dict[str, Any]]: Query results
        """
        connection = self._get_connection()
        return self.query_executor.execute_query(connection, sql, params)

    def create_schema_if_not_exists(self, schema: str) -> None:
        """Create schema if it doesn't exist.

        Note: SQLite doesn't support schemas. This is a no-op.

        Args:
            schema: Schema name (ignored)
        """
        connection = self._get_connection()
        self.schema_operations.create_schema_if_not_exists(connection, schema)

    def schema_exists(self, schema: str) -> bool:
        """Check if a schema exists using PRAGMA database_list.

        Args:
            schema: Schema name (e.g., "main" for primary database)

        Returns:
            bool: True if schema name is in the database list
        """
        self.log.debug(f"Checking if SQLite schema {schema} exists via PRAGMA database_list")
        connection = self._get_connection()
        result = self.query_executor.execute_query(connection, "PRAGMA database_list")
        return any(row.get("name", "").lower() == schema.lower() for row in result)

    def table_exists(self, schema: str, table_name: str) -> bool:
        """Check if a table exists.

        Args:
            schema: Schema name (ignored for SQLite)
            table_name: Table name

        Returns:
            bool: True if table exists
        """
        connection = self._get_connection()
        return self.query_executor.table_exists(connection, schema, table_name)

    def get_database_version(self) -> str:
        """Get SQLite database version information.

        Returns:
            str: SQLite version string
        """
        connection = self._get_connection()
        return self.schema_operations.get_database_version(connection)

    def get_display_url(self) -> str:
        """Return a SQLite URL suitable for logs and reports."""
        get_url = getattr(self.connection_manager, "get_database_url", None)
        if callable(get_url):
            return str(get_url())
        return super().get_display_url()

    def begin_transaction(self) -> None:
        """Begin a database transaction."""
        self._ensure_connection()
        if self.connection:
            # SQLite with isolation_level=None is in autocommit mode
            # We need to explicitly begin a transaction
            self.connection.execute("BEGIN TRANSACTION")
            self._in_transaction = True
            self.log.debug("Transaction started")

    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        if self.connection:
            self.connection.commit()
            self._in_transaction = False
            self.log.debug("Transaction committed")

    def rollback_transaction(self) -> None:
        """Rollback the current transaction."""
        if self.connection:
            self.connection.rollback()
            self._in_transaction = False
            self.log.debug("Transaction rolled back")

    def set_current_schema(self, schema: str) -> None:
        """Set the current schema for the session.

        Note: SQLite doesn't support schemas. This is a no-op.

        Args:
            schema: Schema name (ignored)
        """
        connection = self._get_connection()
        self.schema_operations.set_current_schema(connection, schema)

    def create_migration_lock_table_if_not_exists(self, schema: str) -> None:
        """Create the migration lock table if it doesn't exist.

        Args:
            schema: Schema name (ignored for SQLite)
        """
        connection = self._get_connection()
        self.locking_manager.create_migration_lock_table_if_not_exists(connection, schema)

    def acquire_migration_lock(self, schema: str, wait_timeout_seconds: int = 60) -> bool:
        """Acquire an exclusive migration lock.

        Args:
            schema: Schema name (used for lock naming)
            wait_timeout_seconds: Maximum time to wait

        Returns:
            bool: True if lock acquired
        """
        connection = self._get_connection()
        return self.locking_manager.acquire_migration_lock(connection, schema, wait_timeout_seconds)

    def release_migration_lock(self, schema: str) -> bool:
        """Release the migration lock.

        Args:
            schema: Schema name

        Returns:
            bool: True if lock released
        """
        connection = self._get_connection()
        return self.locking_manager.release_migration_lock(connection, schema)

    def clean_schema(self, schema: str) -> CleanExecutionSummary:
        """Clean all objects from the database.

        Args:
            schema: Schema name (ignored for SQLite)

        Returns:
            CleanExecutionSummary: Summary of cleaning operations
        """
        connection = self._get_connection()
        return self.schema_operations.clean_schema(connection, schema)

    def get_clean_preview(self, schema: str) -> CleanExecutionSummary:
        """Return what a clean would drop, without executing any DROP statements."""
        connection = self._get_connection()
        return self.schema_operations.get_clean_preview(connection, schema)

    def get_applied_migrations(
        self, schema: str, table_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get list of applied migrations from history table.

        Args:
            schema: Schema name (ignored for SQLite)
            table_name: Custom history table name

        Returns:
            List[Dict[str, Any]]: Applied migrations
        """
        connection = self._get_connection()
        return self.history_manager.get_applied_migrations(connection, schema, table_name)

    def get_schema_qualified_name(self, schema: str, object_name: str) -> str:
        """Get a properly formatted object name for SQLite.

        Note: SQLite doesn't use schemas, so just the object name is returned.

        Args:
            schema: Schema name (ignored)
            object_name: Object name

        Returns:
            str: Quoted object name
        """
        return self.query_executor.get_schema_qualified_name(schema, object_name)

    def get_parameter_placeholders(self, count: int) -> str:
        """Get SQLite-specific parameter placeholders.

        Args:
            count: Number of placeholders

        Returns:
            str: Comma-separated placeholders
        """
        return self.schema_operations.get_parameter_placeholders(count)

    def record_migration(
        self,
        schema: str,
        migration_info: Dict[str, Any],
        table_name: Optional[str] = None,
    ) -> None:
        """Record a migration in the history table.

        Args:
            schema: Schema name (ignored for SQLite)
            migration_info: Migration information
            table_name: Custom history table name
        """
        connection = self._get_connection()
        self.history_manager.record_migration(connection, schema, migration_info, table_name)

    def create_history_table(self, schema: str, table_name: str) -> str:
        """Generate the SQL to create a migration history table.

        Args:
            schema: Schema name (ignored for SQLite)
            table_name: Table name

        Returns:
            str: SQL for creating the history table
        """
        return self.history_manager.create_history_table(schema, table_name)

    def create_migration_history_table_if_not_exists(
        self,
        schema: str,
        create_schema: bool = False,
        table_name: str = "dblift_schema_history",
    ) -> None:
        """Create migration history table if it doesn't exist.

        Args:
            schema: Schema name (ignored for SQLite)
            create_schema: Whether to create schema (ignored for SQLite)
            table_name: History table name
        """
        connection = self._get_connection()
        self.history_manager.create_migration_history_table_if_not_exists(
            connection, schema, create_schema, table_name
        )

    def _is_connection_closed(self) -> bool:
        """Check if the connection is closed.

        Returns:
            bool: True if connection is closed or None
        """
        if self.connection is None:
            return True

        try:
            # Try a simple query to check if connection is alive
            self.connection.execute("SELECT 1")
            return False
        except sqlite3.ProgrammingError:
            return True
        except Exception:
            # Intentional: unexpected exception querying SQLite; treat as closed
            return True

    def _close_connection_impl(self) -> None:
        """Close the database connection."""
        if self.connection is not None:
            try:
                self.connection.close()
                self.log.debug("SQLite connection closed")
            except Exception as e:
                self.log.warning(f"Error closing connection: {str(e)}")
            finally:
                self.connection = None

    def close(self) -> None:
        """Close the SQLite connection."""
        self._close_connection_impl()
        if self.connection_manager:
            self.connection_manager.close()
