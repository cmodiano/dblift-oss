"""
PostgreSQL migration history manager.

This module handles PostgreSQL-specific migration history table operations including
creation, recording migrations, retrieving applied migrations, and repair operations.
"""

from typing import Any, Dict, List, Optional

from core.logger import Log
from db.object_naming import get_normalized_object_name
from db.plugins.base_history_manager import BaseHistoryManager
from db.plugins.postgresql.postgresql.locking_manager import _get_advisory_lock_key


class PostgreSqlHistoryManager(BaseHistoryManager):
    """Manages PostgreSQL migration history operations."""

    # PostgreSQL stores unquoted identifiers as lowercase
    DEFAULT_HISTORY_TABLE = "dblift_schema_history"

    def __init__(
        self,
        query_executor: Any,
        schema_operations: Any,
        config: Any,
        log: Optional[Log] = None,
    ) -> None:
        """Initialize the history manager.

        Args:
            query_executor: Query executor instance
            schema_operations: Schema operations instance
            config: Configuration object (reserved; not used by this implementation)
            log: Optional logger
        """
        super().__init__(query_executor, schema_operations, config, log)

    def create_migration_history_table_if_not_exists(
        self,
        connection: Any,
        schema: str,
        create_schema: bool = False,
        table_name: str = "dblift_schema_history",
    ) -> None:
        """Create the migration history table if it doesn't exist.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            create_schema: Whether to create schema if it doesn't exist
            table_name: Custom history table name
        """
        self.log.debug(f"Creating migration history table if not exists: {schema}")

        try:
            if create_schema:
                self.schema_operations.create_schema_if_not_exists(connection, schema)

            # Get database-specific case for dblift object
            dblift_table_name = get_normalized_object_name(table_name, "postgresql")

            lock_key = _get_advisory_lock_key(schema)
            lock_acquired = False
            try:
                self.query_executor.execute_query(
                    connection, f"SELECT pg_advisory_lock({lock_key})"
                )
                lock_acquired = True

                # Check if table exists while holding the schema bootstrap lock.
                table_exists = self.query_executor.table_exists(
                    connection, schema, dblift_table_name
                )
                if table_exists:
                    if create_schema:
                        self._check_baseline_safety(connection, schema, dblift_table_name)
                    self.log.debug(
                        f"Migration history table {schema}.{dblift_table_name} already exists"
                    )
                    return

                # Create the table with PostgreSQL-specific syntax
                qualified_table = self.query_executor.get_schema_qualified_name(
                    schema, dblift_table_name
                )
                create_sql = f"""
                CREATE TABLE {qualified_table} (
                    installed_rank SERIAL PRIMARY KEY,
                    version VARCHAR(50),
                    description VARCHAR(200) NOT NULL,
                    type VARCHAR(20) NOT NULL,
                    script VARCHAR(1000) NOT NULL,
                    checksum INT,
                    installed_by VARCHAR(100) NOT NULL,
                    installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    execution_time INTEGER NOT NULL,
                    success BOOLEAN NOT NULL
                )
                """

                self.query_executor.execute_statement(connection, create_sql)
                self.log.debug(f"Migration history table created successfully in schema {schema}")
            finally:
                if lock_acquired:
                    try:
                        self.query_executor.execute_query(
                            connection, f"SELECT pg_advisory_unlock({lock_key})"
                        )
                    except Exception as unlock_error:
                        self.log.warning(
                            f"Could not release PostgreSQL bootstrap lock: {unlock_error}"
                        )

        except Exception as e:
            error_msg = f"Error creating migration history table in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def record_migration(
        self,
        connection: Any,
        schema: str,
        migration_info: Dict[str, Any],
        table_name: Optional[str] = None,
    ) -> None:
        """Record a migration in the history table.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            migration_info: Dictionary containing migration information
            table_name: Custom history table name
        """
        raw_table = table_name or "dblift_schema_history"
        table = get_normalized_object_name(raw_table, "postgresql")

        if not self.query_executor.table_exists(connection, schema, table):
            self.create_migration_history_table_if_not_exists(connection, schema, True, raw_table)

        try:
            # PostgreSQL doesn't need manual rank calculation with SERIAL
            qualified_table = self.query_executor.get_schema_qualified_name(schema, table)
            insert_sql = f"""
            INSERT INTO {qualified_table} (
                version, description, type, script,
                checksum, installed_by, installed_on, execution_time, success
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?::boolean)
            """

            # Convert boolean to string for PostgreSQL driver compatibility
            success_value = "true" if migration_info.get("success", True) else "false"

            params = self._build_migration_params(migration_info, success_value)

            self.query_executor.execute_statement(connection, insert_sql, params=params)

            self.log.debug(f"Migration recorded in schema {schema}: {migration_info.get('script')}")
        except Exception as e:
            error_msg = f"Error recording migration in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def get_applied_migrations(
        self, connection: Any, schema: str, table_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get list of applied migrations from history table.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            table_name: Custom history table name

        Returns:
            List of dictionaries containing migration information
        """
        raw_table = table_name or "dblift_schema_history"
        table = get_normalized_object_name(raw_table, "postgresql")

        if not self.query_executor.table_exists(connection, schema, table):
            return []

        qualified_table = self.query_executor.get_schema_qualified_name(schema, table)
        query = f"""
        SELECT script, installed_rank, version, description,
               type, checksum, installed_by, installed_on,
               execution_time, success
        FROM {qualified_table}
        ORDER BY installed_rank
        """

        try:
            results: List[Dict[str, Any]] = self.query_executor.execute_query(connection, query)

            # Convert boolean success values properly
            for row in results:
                if "success" in row and row["success"] is not None:
                    row["success"] = bool(row["success"])

            return results
        except Exception as exc:
            error_msg = f"Error getting applied migrations from schema {schema}: {str(exc)}"
            self.log.error(error_msg)
            raise

    def create_history_table(self, schema: str, table_name: str) -> str:
        """Generate the SQL to create a migration history table.

        Args:
            schema: Schema name
            table_name: Table name

        Returns:
            str: SQL for creating the history table
        """
        dblift_table_name = get_normalized_object_name(table_name, "postgresql")
        qualified_table = self.query_executor.get_schema_qualified_name(schema, dblift_table_name)
        return f"""
        CREATE TABLE {qualified_table} (
            installed_rank SERIAL PRIMARY KEY,
            version VARCHAR(50),
            description VARCHAR(200) NOT NULL,
            type VARCHAR(20) NOT NULL,
            script VARCHAR(1000) NOT NULL,
            checksum INT,
            installed_by VARCHAR(100) NOT NULL,
            installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            execution_time INTEGER NOT NULL,
            success BOOLEAN NOT NULL
        )
        """
