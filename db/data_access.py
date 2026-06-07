"""High-level data-access facade backed by dialect-specific providers.

Exposes :class:`DataAccess`, the entry-point the CLI / API layers use to
talk to a database. It resolves the configured dialect through
:class:`ProviderRegistry`, instantiates the matching provider, and wraps
its operations in :class:`OperationResult` objects suitable for logging.
"""

from typing import Any, Dict, Optional

from config import DbliftConfig
from core.logger import Log, NullLog, OperationResult
from db.base_provider import BaseProvider
from db.provider_registry import ProviderRegistry


class DataAccess:
    """Data access layer for database operations using providers."""

    def __init__(self, config: DbliftConfig, log: Optional[Log] = None):
        """Initialize data access with configuration.

        Args:
            config: Application configuration
            log: Optional logger
        """
        self.config = config
        self.log = log if log is not None else NullLog()
        self.provider: Optional[BaseProvider] = None

    @staticmethod
    def get_available_drivers() -> Dict[str, bool]:
        """Get native driver availability for all supported database types.

        Returns:
            Dictionary mapping database types to boolean availability status
        """
        return ProviderRegistry.get_available_drivers()

    def initialize(self) -> OperationResult:
        """Initialize the data access layer.

        Returns:
            OperationResult indicating success or failure
        """
        try:
            self.provider = ProviderRegistry.create_provider(self.config, self.log)
            # Create a result object
            result = OperationResult()
            result.success = True
            return result
        except Exception as e:
            error_msg = f"Failed to initialize data access: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def create_connection(self) -> OperationResult:
        """Create a database connection.

        Returns:
            OperationResult with connection in the data field if successful
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            connection = self.provider.create_connection()
            # Create a result object
            result = OperationResult()
            result.success = True
            result.data = connection
            return result
        except Exception as e:
            error_msg = f"Failed to create database connection: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def execute_query(self, query: str, params: Optional[Any] = None) -> OperationResult:
        """Execute a SQL query and return the results.

        Args:
            query: SQL query to execute
            params: Optional parameters for the query (should be a list or None)

        Returns:
            OperationResult with query results if successful
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            # Only allow list or None for params
            if params is not None and not isinstance(params, list):
                raise ValueError(
                    "Only positional (list) parameters are supported for execute_query."
                )
            results = self.provider.execute_query(query, params)
            # Create a result object
            result = OperationResult()
            result.success = True
            result.data = results
            return result
        except Exception as e:
            error_msg = f"Failed to execute query: {str(e)}"
            self.log.error(error_msg)
            self.log.debug(f"Query: {query}")
            if params:
                self.log.debug(f"Parameters: {params}")
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def execute_statement(
        self, statement: str, params: Optional[Dict[str, Any]] = None
    ) -> OperationResult:
        """Execute a SQL statement.

        Args:
            statement: SQL statement to execute
            params: Optional parameters for the statement

        Returns:
            OperationResult with affected row count in the data field if successful
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            self.log.debug(
                f"[DEBUG] execute_statement params type: {type(params)}, value: {params}"
            )
            # If params is a dict, raise an error (or convert if you want to support named params)
            if isinstance(params, dict):
                raise ValueError(
                    "Dict parameters are not supported for positional ? placeholders. Use a list instead."
                )
            affected_rows = self.provider.execute_statement(statement, params)
            # Create a result object
            result = OperationResult()
            result.success = True
            result.data = affected_rows
            return result
        except Exception as e:
            error_msg = f"Failed to execute statement: {str(e)}"
            self.log.error(error_msg)
            self.log.debug(f"Statement: {statement}")
            if params:
                self.log.debug(f"Parameters: {params}")
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def create_schema(self, schema_name: str) -> OperationResult:
        """Create a database schema if it doesn't exist.

        Args:
            schema_name: Name of the schema to create

        Returns:
            OperationResult indicating success or failure
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            self.provider.create_schema_if_not_exists(schema_name)
            # Create a result object
            result = OperationResult()
            result.success = True
            return result
        except Exception as e:
            error_msg = f"Failed to create schema {schema_name}: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def create_history_table(self, schema_name: str) -> OperationResult:
        """Create a history table for the specified schema.

        Args:
            schema_name: Schema name

        Returns:
            OperationResult indicating success or failure
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            self.provider.create_history_table_if_not_exists(schema_name)
            # Create a result object
            result = OperationResult()
            result.success = True
            return result
        except Exception as e:
            error_msg = f"Failed to create history table in schema {schema_name}: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def set_current_schema(self, schema_name: str) -> OperationResult:
        """Set the current schema for the database session.

        This is particularly important for Oracle, where the schema needs to be set at the session level.
        For other databases like SQL Server, this might be a no-op.

        Args:
            schema_name: Name of the schema to set as current

        Returns:
            OperationResult indicating success or failure
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            self.provider.set_current_schema(schema_name)
            # Create a result object
            result = OperationResult()
            result.success = True
            return result
        except Exception as e:
            error_msg = f"Failed to set current schema to {schema_name}: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def close(self) -> None:
        """Close any open resources."""
        if self.provider:
            self.provider.close()

    def create_migration_lock_table(self, schema_name: str) -> OperationResult:
        """Create the migration lock table if it doesn't exist.

        Args:
            schema_name: Schema name

        Returns:
            OperationResult indicating success or failure
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            self.provider.create_migration_lock_table_if_not_exists(schema_name)
            # Create a result object
            result = OperationResult()
            result.success = True
            return result
        except Exception as e:
            error_msg = f"Failed to create migration lock table in schema {schema_name}: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def acquire_migration_lock(
        self, schema_name: str, wait_timeout_seconds: int = 60
    ) -> OperationResult:
        """Acquire a lock for migration to prevent concurrent migrations.

        Args:
            schema_name: Schema name
            wait_timeout_seconds: How long to wait for lock acquisition in seconds

        Returns:
            OperationResult indicating success or failure
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            acquired = self.provider.acquire_migration_lock(schema_name, wait_timeout_seconds)
            if acquired:
                # Create a result object
                result = OperationResult()
                result.success = True
                return result
            else:
                error_msg = f"Failed to acquire migration lock in schema {schema_name} after {wait_timeout_seconds} seconds"
                self.log.error(error_msg)
                # Create a result object
                result = OperationResult()
                result.success = False
                result.error_message = error_msg
                return result
        except Exception as e:
            error_msg = f"Error acquiring migration lock in schema {schema_name}: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result

    def release_migration_lock(self, schema_name: str) -> OperationResult:
        """Release the migration lock.

        Args:
            schema_name: Schema name

        Returns:
            OperationResult indicating success or failure
        """
        if not self.provider:
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = "Data access not initialized. Call initialize() first."
            return result

        try:
            released = self.provider.release_migration_lock(schema_name)
            if released:
                # Create a result object
                result = OperationResult()
                result.success = True
                return result
            else:
                error_msg = f"Failed to release migration lock in schema {schema_name}"
                self.log.error(error_msg)
                # Create a result object
                result = OperationResult()
                result.success = False
                result.error_message = error_msg
                return result
        except Exception as e:
            error_msg = f"Error releasing migration lock in schema {schema_name}: {str(e)}"
            self.log.error(error_msg)
            # Create a result object
            result = OperationResult()
            result.success = False
            result.error_message = error_msg
            return result
