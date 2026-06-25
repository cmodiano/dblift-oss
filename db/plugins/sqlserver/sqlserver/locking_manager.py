"""
SQL Server migration locking manager.

This module handles SQL Server-specific migration locking using application locks
to ensure only one migration process can run at a time per schema.
"""

import os
from typing import Any, Optional

from core.logger import Log, NullLog
from db.object_naming import get_normalized_object_name
from db.plugins.base_locking_manager import BaseLockingManager


class SqlServerLockingManager(BaseLockingManager):
    """Manages SQL Server migration locking operations."""

    # SQL Server stores identifiers as specified (case-insensitive by default)
    DEFAULT_LOCK_TABLE = "dblift_migration_lock"
    DIALECT = "sqlserver"

    def __init__(self, query_executor: Any, log: Optional[Log] = None) -> None:
        """Initialize the locking manager.

        Args:
            query_executor: Query executor instance for database operations
            log: Optional logger
        """
        self.query_executor = query_executor
        self.log = log if log is not None else NullLog()

    def create_migration_lock_table_if_not_exists(self, connection: Any, schema: str) -> None:
        """Create the migration lock table if it doesn't exist.

        This table is used to track active migration locks and prevent
        concurrent migrations on the same schema.

        Args:
            schema: Target schema name
        """
        self.log.debug(f"Creating migration lock table if not exists in schema: {schema}")

        try:
            # SQL Server-specific table creation with proper data types and constraints
            dblift_lock_table = get_normalized_object_name("dblift_migration_lock", "sqlserver")
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            create_table_sql = f"""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES
                          WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{dblift_lock_table}')
            BEGIN
                IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = '{schema}')
                BEGIN
                    EXEC('CREATE SCHEMA [{schema}]')
                END
                CREATE TABLE {qualified_table} (
                    lock_name NVARCHAR(128) NOT NULL PRIMARY KEY,
                    acquired_at DATETIME2 DEFAULT GETDATE() NOT NULL,
                    acquired_by NVARCHAR(256) DEFAULT SUSER_NAME() NOT NULL,
                    session_id INT DEFAULT @@SPID NOT NULL,
                    process_id NVARCHAR(64),
                    lock_mode INT DEFAULT 1 NOT NULL
                )
            END
            """

            self.query_executor.execute_statement(connection, create_table_sql)
            self.log.debug(f"Migration lock table ensured in schema: {schema}")

        except Exception as e:
            error_msg = f"Error creating migration lock table in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def acquire_migration_lock(
        self, connection: Any, schema: str, wait_timeout_seconds: float = 60.0
    ) -> bool:
        """Acquire an exclusive migration lock for the specified schema.

        Uses SQL Server's sp_getapplock procedure to create an application-level lock
        that prevents concurrent migrations on the same schema. Falls back to
        table-based locking if native app locks are not available.

        Args:
            schema: Target schema name
            wait_timeout_seconds: Maximum time to wait for lock acquisition

        Returns:
            bool: True if lock was acquired successfully, False otherwise
        """
        self.log.debug(f"Attempting to acquire migration lock for schema: {schema}")

        try:
            # Get the lock name for this schema
            lock_name = f"dblift_migration_lock_{schema}"

            self.log.debug(f"Using lock name: {lock_name}")

            # Convert timeout to milliseconds for SQL Server
            timeout_ms = wait_timeout_seconds * 1000

            # Try to acquire the lock using native sp_getapplock first
            try:
                lock_sql = """
                DECLARE @result INT;
                EXEC @result = sp_getapplock
                    @Resource = ?,
                    @LockMode = 'Exclusive',
                    @LockOwner = 'Session',
                    @LockTimeout = ?;
                SELECT @result AS lock_result;
                """

                result = self.query_executor.execute_query(
                    connection, lock_sql, params=[lock_name, timeout_ms]
                )

                if result and len(result) > 0:
                    lock_result = result[0].get("lock_result", result[0].get("LOCK_RESULT", -999))

                    if lock_result == 0:
                        # Lock acquired successfully using native app lock
                        self.log.debug(
                            f"Successfully acquired migration lock for schema: {schema} using native app lock"
                        )
                        return True
                    elif lock_result == 1:
                        # Lock was already granted to this session
                        self.log.debug(f"Migration lock already owned for schema: {schema}")
                        return True
                    else:
                        # Lock acquisition failed - fall back to table-based locking
                        error_messages = {
                            -1: "Request timed out",
                            -2: "Request canceled",
                            -3: "Request was a deadlock victim",
                            -999: "Parameter validation or other error",
                        }
                        error_msg = error_messages.get(
                            lock_result, f"Unknown error code: {lock_result}"
                        )
                        self.log.warning(
                            f"Failed to acquire native app lock for schema {schema}: {error_msg}; falling back to table-based locking"
                        )
                        # Fall back to table-based locking
                        return self._acquire_table_based_lock(
                            connection, schema, lock_name, int(wait_timeout_seconds)
                        )
                else:
                    self.log.warning(
                        "No result returned from lock acquisition attempt; falling back"
                    )
                    # Fall back to table-based locking
                    return self._acquire_table_based_lock(
                        connection, schema, lock_name, int(wait_timeout_seconds)
                    )

            except Exception as e:
                self.log.warning(
                    f"Error acquiring native app lock: {str(e)}; falling back to table-based locking"
                )
                # Fall back to table-based locking
                return self._acquire_table_based_lock(
                    connection, schema, lock_name, int(wait_timeout_seconds)
                )

        except Exception as e:
            self.log.warning(
                f"Error acquiring migration lock for schema {schema}: {str(e)}; falling back to table-based locking"
            )
            # Fall back to table-based locking
            lock_name = f"dblift_migration_lock_{schema}"
            return self._acquire_table_based_lock(
                connection, schema, lock_name, int(wait_timeout_seconds)
            )

    def _acquire_table_based_lock(
        self, connection: Any, schema: str, lock_name: str, wait_timeout_seconds: int
    ) -> bool:
        """Acquire lock using table-based mechanism as fallback.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Target schema name
            lock_name: Lock name for this schema
            wait_timeout_seconds: Maximum time to wait for lock acquisition

        Returns:
            bool: True if lock was acquired successfully, False otherwise
        """
        self.log.debug("Using table-based locking mechanism as fallback")

        try:
            # Create lock table if it doesn't exist (only needed for fallback)
            self.create_migration_lock_table_if_not_exists(connection, schema)

            dblift_lock_table = get_normalized_object_name("dblift_migration_lock", "sqlserver")
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            # Use MERGE to handle cases where stale lock records exist from aborted sessions
            merge_sql = f"""
            MERGE {qualified_table} AS target
            USING (SELECT ? AS lock_name, GETDATE() AS acquired_at, SUSER_NAME() AS acquired_by,
                   @@SPID AS session_id, ? AS process_id, 1 AS lock_mode) AS source
            ON target.lock_name = source.lock_name
            WHEN MATCHED THEN
                UPDATE SET
                    acquired_at = source.acquired_at,
                    acquired_by = source.acquired_by,
                    session_id = source.session_id,
                    process_id = source.process_id,
                    lock_mode = source.lock_mode
            WHEN NOT MATCHED THEN
                INSERT (lock_name, acquired_at, acquired_by, session_id, process_id, lock_mode)
                VALUES (source.lock_name, source.acquired_at, source.acquired_by,
                        source.session_id, source.process_id, source.lock_mode);
            """

            process_id = str(os.getpid())
            self.query_executor.execute_statement(
                connection, merge_sql, params=[lock_name, process_id]
            )

            self.log.debug(
                f"Successfully acquired migration lock for schema: {schema} using table-based locking"
            )
            return True

        except Exception as e:
            error_msg = f"Error acquiring table-based migration lock for schema {schema}: {str(e)}"
            self.log.error(error_msg)
            return False

    def release_migration_lock(self, connection: Any, schema: str) -> bool:
        """Release the migration lock for the specified schema.

        Tries to release native app lock first, then cleans up table-based lock if it exists.

        Args:
            schema: Target schema name

        Returns:
            bool: True if lock was released successfully, False otherwise
        """
        self.log.debug(f"Attempting to release migration lock for schema: {schema}")

        released = False

        try:
            lock_name = f"dblift_migration_lock_{schema}"

            # Try to release the native app lock first
            try:
                release_sql = """
                DECLARE @result INT;
                EXEC @result = sp_releaseapplock
                    @Resource = ?,
                    @LockOwner = 'Session';
                SELECT @result AS release_result;
                """

                result = self.query_executor.execute_query(
                    connection, release_sql, params=[lock_name]
                )

                if result and len(result) > 0:
                    release_result = result[0].get(
                        "release_result", result[0].get("RELEASE_RESULT", -999)
                    )

                    if release_result == 0:
                        # Lock released successfully
                        self.log.debug(
                            f"Successfully released native app lock for schema: {schema}"
                        )
                        released = True
                    else:
                        error_messages = {-999: "Lock was not held by this session"}
                        error_msg = error_messages.get(
                            release_result, f"Unknown error code: {release_result}"
                        )
                        self.log.debug(f"Native app lock release: {error_msg}")
            except Exception as e:
                self.log.debug(f"Could not release native app lock: {str(e)}")

            # Also try to clean up table-based lock (if it was used as fallback)
            try:
                dblift_lock_table = get_normalized_object_name("dblift_migration_lock", "sqlserver")
                if self.query_executor.table_exists(connection, schema, dblift_lock_table):
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, dblift_lock_table
                    )

                    # Try to delete by session_id first (normal case)
                    delete_sql = (
                        f"DELETE FROM {qualified_table} WHERE lock_name = ? AND session_id = @@SPID"
                    )
                    rows_deleted = self.query_executor.execute_statement(
                        connection, delete_sql, params=[lock_name]
                    )

                    if rows_deleted == 0:
                        # Try to clean up any stale records for this lock_name
                        delete_sql = f"DELETE FROM {qualified_table} WHERE lock_name = ?"
                        rows_deleted = self.query_executor.execute_statement(
                            connection, delete_sql, params=[lock_name]
                        )

                    if rows_deleted > 0:
                        self.log.debug(f"Cleaned up table-based lock record for schema: {schema}")
                        released = True

                        # Drop the lock table since it was only used as fallback
                        self._drop_lock_table_if_exists(connection, schema)
            except Exception as e:
                self.log.debug(f"Could not clean up table-based lock: {str(e)}")

            return released

        except Exception as e:
            error_msg = f"Error releasing migration lock for schema {schema}: {str(e)}"
            self.log.error(error_msg)
            return False
