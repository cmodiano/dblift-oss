"""
PostgreSQL migration locking manager.

This module handles PostgreSQL-specific migration locking using advisory locks
to ensure only one migration process can run at a time per schema.
"""

import hashlib
import os
import time
from typing import Any, Optional

from core.logger import Log, NullLog
from db.object_naming import get_normalized_object_name
from db.plugins.base_locking_manager import BaseLockingManager


def _get_advisory_lock_key(schema: str) -> int:
    """Return a deterministic PostgreSQL advisory lock key for a DBLift schema."""
    lock_name = f"dblift_migration_lock:{schema}"
    digest = hashlib.sha256(lock_name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class PostgreSqlLockingManager(BaseLockingManager):
    """Manages PostgreSQL migration locking operations."""

    # PostgreSQL stores unquoted identifiers as lowercase
    DEFAULT_LOCK_TABLE = "dblift_migration_lock"
    DIALECT = "postgresql"

    def __init__(self, query_executor: Any, log: Optional[Log] = None) -> None:
        """Initialize the locking manager.

        Args:
            query_executor: Query executor instance for database operations
            log: Optional logger
        """
        self.query_executor: Any = query_executor
        self.log: Log = log if log is not None else NullLog()

    def create_migration_lock_table_if_not_exists(self, connection: Any, schema: str) -> None:
        """Create the migration lock table if it doesn't exist.

        This table is used to track active migration locks and prevent
        concurrent migrations on the same schema.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Target schema name
        """
        self.log.debug(f"Creating migration lock table if not exists in schema: {schema}")

        try:
            # PostgreSQL-specific table creation with proper data types and constraints
            dblift_lock_table = get_normalized_object_name("dblift_migration_lock", "postgresql")
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {qualified_table} (
                lock_name VARCHAR(128) NOT NULL PRIMARY KEY,
                acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                acquired_by VARCHAR(256) DEFAULT CURRENT_USER NOT NULL,
                session_pid INTEGER DEFAULT pg_backend_pid() NOT NULL,
                process_id VARCHAR(64),
                lock_mode INTEGER DEFAULT 1 NOT NULL
            )
            """

            self.query_executor.execute_statement(connection, create_table_sql)
            self.log.debug(f"Migration lock table ensured in schema: {schema}")

        except Exception as e:
            error_msg = f"Error creating migration lock table in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def acquire_migration_lock(
        self, connection: Any, schema: str, wait_timeout_seconds: int = 60
    ) -> bool:
        """Acquire an exclusive migration lock for the specified schema.

        Uses PostgreSQL's advisory locks to create an application-level lock
        that prevents concurrent migrations on the same schema. Falls back to
        table-based locking if native advisory locks are not available.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Target schema name
            wait_timeout_seconds: Maximum time to wait for lock acquisition

        Returns:
            bool: True if lock was acquired successfully, False otherwise
        """
        self.log.debug(f"Attempting to acquire migration lock for schema: {schema}")

        try:
            lock_key = _get_advisory_lock_key(schema)

            self.log.debug(f"Using lock key: {lock_key}")

            # Try to acquire the advisory lock first (native PostgreSQL locking)
            start_time = time.time()

            while time.time() - start_time < wait_timeout_seconds:
                try:
                    # Try to acquire the lock (non-blocking first)
                    # PostgreSQL advisory lock functions need the lock key embedded directly in SQL
                    lock_sql = f"SELECT pg_try_advisory_lock({lock_key}) as lock_acquired"
                    result = self.query_executor.execute_query(connection, lock_sql)

                    if result and len(result) > 0:
                        lock_acquired = result[0].get(
                            "lock_acquired", result[0].get("LOCK_ACQUIRED", False)
                        )

                        if lock_acquired:
                            # Lock acquired successfully using native advisory lock
                            self.log.debug(
                                f"Successfully acquired migration lock for schema: {schema} using native advisory lock"
                            )
                            return True
                        else:
                            # Lock not available, wait a bit and try again
                            elapsed = int(time.time() - start_time)
                            self.log.debug(f"Lock not available, waiting... (elapsed: {elapsed}s)")
                            time.sleep(1)
                            continue
                    else:
                        self.log.warning("No result returned from advisory lock attempt")
                        time.sleep(1)
                        continue

                except Exception as e:
                    self.log.warning(
                        f"Error during native lock acquisition attempt: {str(e)}; falling back to table-based locking"
                    )
                    # Fall back to table-based locking
                    break

            # If we reach here, either timeout exceeded or native locking failed
            # Fall back to table-based locking
            self.log.debug("Falling back to table-based locking mechanism")
            return self._acquire_table_based_lock(connection, schema, wait_timeout_seconds)

        except Exception as e:
            self.log.warning(
                f"Error acquiring native migration lock for schema {schema}: {str(e)}; falling back to table-based locking"
            )
            # Fall back to table-based locking
            return self._acquire_table_based_lock(connection, schema, wait_timeout_seconds)

    def _acquire_table_based_lock(
        self, connection: Any, schema: str, wait_timeout_seconds: int
    ) -> bool:
        """Acquire lock using table-based mechanism as fallback.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Target schema name
            wait_timeout_seconds: Maximum time to wait for lock acquisition

        Returns:
            bool: True if lock was acquired successfully, False otherwise
        """
        self.log.debug("Using table-based locking mechanism as fallback")

        try:
            # Create lock table if it doesn't exist (only needed for fallback)
            self.create_migration_lock_table_if_not_exists(connection, schema)

            lock_name = f"dblift_migration_lock_{schema}"
            start_time = time.time()

            while time.time() - start_time < wait_timeout_seconds:
                try:
                    dblift_lock_table = get_normalized_object_name(
                        "dblift_migration_lock", "postgresql"
                    )
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, dblift_lock_table
                    )
                    # Try to insert lock record (will fail if lock already exists)
                    insert_sql = f"""
                    INSERT INTO {qualified_table}
                    (lock_name, acquired_at, acquired_by, session_pid, process_id, lock_mode)
                    VALUES (?, CURRENT_TIMESTAMP, CURRENT_USER, pg_backend_pid(), ?, 1)
                    """

                    process_id = str(os.getpid())
                    self.query_executor.execute_statement(
                        connection, insert_sql, params=[lock_name, process_id]
                    )

                    # CRITICAL: Explicitly commit the lock row immediately when using table-based locking
                    # This ensures the lock is committed before migrations execute in their own transactions
                    # UPDATED: Use passed connection instead of query_executor.connection
                    if connection:
                        try:
                            connection.commit()
                            self.log.debug("Committed lock acquisition transaction")
                        except Exception as commit_e:
                            self.log.warning(f"Could not commit lock acquisition: {commit_e}")
                            # Continue anyway - lock might still be acquired

                    self.log.debug(
                        f"Successfully acquired migration lock for schema: {schema} using table-based locking"
                    )
                    return True

                except Exception as e:
                    error_str = str(e).lower()
                    if (
                        "unique" in error_str
                        or "duplicate" in error_str
                        or "violates unique constraint" in error_str
                    ):
                        # Lock is held by another process, wait and retry
                        elapsed = int(time.time() - start_time)
                        self.log.debug(
                            f"Lock held by another process, waiting... (elapsed: {elapsed}s)"
                        )
                        time.sleep(1)
                        continue
                    else:
                        # Unexpected error
                        self.log.warning(f"Error during table-based lock acquisition: {str(e)}")
                        time.sleep(1)
                        continue

            # Timeout exceeded
            self.log.warning(
                f"Failed to acquire table-based migration lock for schema {schema} within {wait_timeout_seconds} seconds"
            )
            return False

        except Exception as e:
            error_msg = f"Error acquiring table-based migration lock for schema {schema}: {str(e)}"
            self.log.error(error_msg)
            return False

    def release_migration_lock(self, connection: Any, schema: str) -> bool:
        """Release the migration lock for the specified schema.

        Tries to release native advisory lock first, then cleans up table-based lock if it exists.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Target schema name

        Returns:
            bool: True if lock was released successfully, False otherwise
        """
        self.log.debug(f"Attempting to release migration lock for schema: {schema}")

        released = False

        try:
            lock_key = _get_advisory_lock_key(schema)

            # Try to release the native advisory lock first
            try:
                release_sql = f"SELECT pg_advisory_unlock({lock_key}) as lock_released"
                result = self.query_executor.execute_query(connection, release_sql)

                if result and len(result) > 0:
                    lock_released = result[0].get(
                        "lock_released", result[0].get("LOCK_RELEASED", False)
                    )

                    if lock_released:
                        self.log.debug(
                            f"Successfully released native advisory lock for schema: {schema}"
                        )
                        released = True
                    else:
                        self.log.debug(f"Native advisory lock was not held for schema {schema}")
            except Exception as e:
                self.log.debug(f"Could not release native advisory lock: {str(e)}")

            # Also try to clean up table-based lock (if it was used as fallback)
            try:
                dblift_lock_table = get_normalized_object_name(
                    "dblift_migration_lock", "postgresql"
                )
                if self.query_executor.table_exists(connection, schema, dblift_lock_table):
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, dblift_lock_table
                    )
                    delete_sql = f"DELETE FROM {qualified_table} WHERE lock_name = ? AND session_pid = pg_backend_pid()"
                    rows_deleted = self.query_executor.execute_statement(
                        connection, delete_sql, params=[f"dblift_migration_lock_{schema}"]
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
