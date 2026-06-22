"""
DB2 migration locking manager.

This module handles DB2-specific migration locking functionality using multiple
locking mechanisms including SYSTOOLS.LOCKING and table-based locking.

Note: DB2 LUW does not have built-in advisory lock functions like PostgreSQL's
pg_advisory_lock() or Oracle's DBMS_LOCK, so we rely on table-based mechanisms.
"""

import os
import socket
import time
from typing import Any, Optional

from core.logger import Log, NullLog
from db.exceptions import DB_OPERATION_EXCEPTIONS
from db.plugins.base_locking_manager import BaseLockingManager


class Db2LockingManager(BaseLockingManager):
    """Manages DB2-specific migration locking using multiple mechanisms."""

    # DB2 stores unquoted identifiers as UPPERCASE
    DEFAULT_LOCK_TABLE = "DBLIFT_MIGRATION_LOCK"
    MIGRATION_LOCK_TABLE = DEFAULT_LOCK_TABLE
    DIALECT = "db2"

    def __init__(self, query_executor: Any, log: Optional[Log] = None) -> None:
        """Initialize the locking manager.

        Args:
            query_executor: Query executor instance
            log: Optional logger
        """
        self.query_executor = query_executor
        self.log = log if log is not None else NullLog()

    def create_migration_lock_table_if_not_exists(self, connection: Any, schema: str) -> None:
        """Create the migration lock table if it doesn't exist.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
        """
        self.log.debug(f"Checking migration lock table in schema {schema}")

        # Use database-specific default case for dblift objects
        from db.object_naming import get_normalized_object_name

        dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "db2")

        # Check if lock table exists
        if self.query_executor.table_exists(connection, schema, dblift_lock_table):
            self.log.debug(f"Migration lock table already exists in schema {schema}")
            return

        # Create lock table with DB2-specific syntax
        qualified_table = self.query_executor.get_schema_qualified_name(schema, dblift_lock_table)
        create_table_sql = f"""
        CREATE TABLE {qualified_table} (
            lock_name VARCHAR(128) NOT NULL,
            acquired_at TIMESTAMP NOT NULL,
            acquired_by VARCHAR(128) NOT NULL,
            PRIMARY KEY (lock_name)
        )
        """

        try:
            self.query_executor.execute_statement(connection, create_table_sql)
            # CRITICAL: Commit table creation immediately (DB2 uses autoCommit=False)
            try:
                connection.commit()
            except DB_OPERATION_EXCEPTIONS as e:
                self.log.debug(f"Commit failed (non-critical, connection may be closed): {e}")
            self.log.debug(f"Migration lock table created successfully in schema {schema}")
        except DB_OPERATION_EXCEPTIONS as e:
            # Rollback on error
            try:
                connection.rollback()
            except DB_OPERATION_EXCEPTIONS as rb_e:
                self.log.debug(f"Rollback failed (non-critical, connection may be closed): {rb_e}")
            error_msg = f"Error creating migration lock table in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def acquire_migration_lock(
        self, connection: Any, schema: str, wait_timeout_seconds: int = 60
    ) -> bool:
        """Acquire a lock for migration operations using DB2 locking mechanisms.

        Tries multiple locking mechanisms in order of preference:
        1. SYSTOOLS.LOCKING table (if available)
        2. Table-based locking (always available)

        Note: DB2 LUW does not have built-in advisory lock functions like PostgreSQL
        or Oracle, so we rely on table-based locking mechanisms.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            wait_timeout_seconds: Timeout in seconds to wait for lock

        Returns:
            True if lock acquired, False otherwise
        """
        self.log.debug(f"Attempting to acquire migration lock in schema {schema}")

        # Try SYSTOOLS.LOCKING table first (if available)
        if self._try_systools_locking_acquire(connection, schema, wait_timeout_seconds):
            return True

        # Try table-based locking as fallback (always available)
        if self._try_table_based_locking_acquire(connection, schema, wait_timeout_seconds):
            return True

        # All mechanisms failed
        self.log.error(f"All locking mechanisms failed for schema {schema}")
        return False

    def _try_systools_locking_acquire(
        self, connection: Any, schema: str, wait_timeout_seconds: int
    ) -> bool:
        """Try to acquire lock using SYSTOOLS.LOCKING table.

        Args:
            schema: Schema name
            wait_timeout_seconds: Timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            check_systools_sql = """
            SELECT 1
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = 'SYSTOOLS'
            AND TABNAME = 'LOCKING'
            """

            systools_exists = (
                len(self.query_executor.execute_query(connection, check_systools_sql)) > 0
            )

            if systools_exists:
                # Generate a unique lock ID for this schema
                lock_name = f"DBLIFT_MIGRATION_{schema.upper()}"

                hostname = socket.gethostname()
                username = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
                process_id = os.getpid()
                lock_identity = f"{username}@{hostname}:{process_id}"

                # First, clean up any stale locks older than the timeout period
                cleanup_sql = """
                DELETE FROM SYSTOOLS.LOCKING
                WHERE NAME = ?
                AND TIMESTAMP < CURRENT TIMESTAMP - ? SECONDS
                """

                self.query_executor.execute_statement(
                    connection, cleanup_sql, params=[lock_name, wait_timeout_seconds]
                )

                # Now try to insert our lock
                insert_lock_sql = """
                INSERT INTO SYSTOOLS.LOCKING (NAME, COMMENT, TIMESTAMP)
                VALUES (?, ?, CURRENT TIMESTAMP)
                """

                try:
                    self.query_executor.execute_statement(
                        connection, insert_lock_sql, params=[lock_name, lock_identity]
                    )
                    connection.commit()

                    self.log.debug(
                        f"Migration lock acquired via SYSTOOLS.LOCKING by {lock_identity}"
                    )
                    return True
                except DB_OPERATION_EXCEPTIONS as e:
                    connection.rollback()
                    self.log.debug(f"Could not acquire lock via SYSTOOLS.LOCKING, error: {str(e)}")
                    return False

            return False

        except DB_OPERATION_EXCEPTIONS as e:
            self.log.debug(f"SYSTOOLS.LOCKING table not available, error: {str(e)}")
            return False

    def _ensure_clean_transaction(self, connection: Any) -> None:
        """Ensure no uncommitted transaction exists before lock operations.

        This is critical for DB2 as row-level locks acquired via FOR UPDATE
        are transaction-scoped and persist until commit/rollback.

        Args:
            connection: Active database connection (provided by Provider)

        Returns:
            None
        """
        try:
            if not connection.getAutoCommit():
                # Rollback any existing uncommitted transaction
                connection.rollback()
                self.log.debug("Rolled back existing uncommitted transaction")
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.debug(f"Error checking/rolling back transaction: {e}")

    def _cleanup_stale_locks(self, connection: Any, schema: str, timeout_seconds: int) -> None:
        """Clean up stale locks that may have been left by crashed processes.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            timeout_seconds: Maximum age of locks to consider stale
        """
        try:
            # Use database-specific default case for dblift objects
            from db.object_naming import get_normalized_object_name

            dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "db2")

            # Check if table exists before attempting cleanup
            if not self.query_executor.table_exists(connection, schema, dblift_lock_table):
                self.log.debug("Lock table does not exist, skipping stale lock cleanup")
                return

            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            # Delete locks older than timeout period
            # Use DB2's timestamp arithmetic
            cleanup_sql = f"""
            DELETE FROM {qualified_table}
            WHERE lock_name = 'migration'
            AND acquired_at < CURRENT TIMESTAMP - {timeout_seconds} SECONDS
            """

            try:
                affected = self.query_executor.execute_statement(connection, cleanup_sql)
                try:
                    connection.commit()
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.debug(f"Commit failed (non-critical, connection may be closed): {e}")
                if affected > 0 and self.log:
                    self.log.debug(f"Cleaned up {affected} stale lock(s)")
            except DB_OPERATION_EXCEPTIONS as e:
                try:
                    connection.rollback()
                except DB_OPERATION_EXCEPTIONS as rb_e:
                    self.log.debug(
                        f"Rollback failed (non-critical, connection may be closed): {rb_e}"
                    )
                # SQLCODE=-204 means table doesn't exist, which is fine
                error_str = str(e).lower()
                if "sql204" not in error_str and "-204" not in error_str:
                    self.log.debug(f"Could not cleanup stale locks: {e}")
        except DB_OPERATION_EXCEPTIONS as e:
            # SQLCODE=-204 means table doesn't exist, which is fine
            error_str = str(e).lower()
            if "sql204" not in error_str and "-204" not in error_str:
                self.log.debug(f"Error in stale lock cleanup: {e}")

    def _try_table_based_locking_acquire(
        self, connection: Any, schema: str, wait_timeout_seconds: int
    ) -> bool:
        """Try to acquire lock using table-based locking mechanism.

        Uses MERGE (upsert) for atomic lock acquisition, with proper transaction
        management and stale lock cleanup.

        Args:
            schema: Schema name
            wait_timeout_seconds: Timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        self.log.debug("Using table-based locking mechanism")

        # Create lock table if it doesn't exist
        self.create_migration_lock_table_if_not_exists(connection, schema)

        # Ensure clean transaction state before lock operations
        self._ensure_clean_transaction(connection)

        # Use database-specific default case for dblift objects
        from db.object_naming import get_normalized_object_name

        dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "db2")

        # Clean up stale locks before attempting acquisition (only if table exists)
        if self.query_executor.table_exists(connection, schema, dblift_lock_table):
            self._cleanup_stale_locks(connection, schema, wait_timeout_seconds)

        try:
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            hostname = socket.gethostname()
            username = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
            process_id = os.getpid()
            lock_identity = f"{username}@{hostname}:{process_id}"

            # Use MERGE (upsert) for atomic lock acquisition
            merge_sql = f"""
            MERGE INTO {qualified_table} AS target
            USING (
                SELECT 'migration' AS lock_name, CURRENT TIMESTAMP AS acquired_at, ? AS acquired_by
                FROM SYSIBM.SYSDUMMY1
            ) AS source
            ON target.lock_name = source.lock_name
            WHEN MATCHED THEN
                UPDATE SET acquired_at = source.acquired_at, acquired_by = source.acquired_by
            WHEN NOT MATCHED THEN
                INSERT (lock_name, acquired_at, acquired_by)
                VALUES (source.lock_name, source.acquired_at, source.acquired_by)
            """

            start_time = time.time()

            while time.time() - start_time < wait_timeout_seconds:
                try:
                    # Ensure clean transaction state for each retry
                    self._ensure_clean_transaction(connection)

                    # Set a short lock timeout to avoid long waits
                    try:
                        self.query_executor.execute_statement(
                            connection, "SET CURRENT LOCK TIMEOUT 1"
                        )
                    except DB_OPERATION_EXCEPTIONS as e:
                        self.log.debug(f"SET CURRENT LOCK TIMEOUT not supported, continuing: {e}")

                    # Attempt MERGE operation
                    self.query_executor.execute_statement(
                        connection, merge_sql, params=[lock_identity]
                    )

                    # CRITICAL: Explicitly commit the lock row immediately (DB2 uses autoCommit=False)
                    try:
                        connection.commit()
                    except DB_OPERATION_EXCEPTIONS as e:
                        self.log.debug(
                            f"Commit failed (non-critical, connection may be closed): {e}"
                        )

                    self.log.debug(f"Migration lock acquired by {lock_identity}")
                    return True

                except DB_OPERATION_EXCEPTIONS as e:
                    # CRITICAL: Always rollback on error to prevent lock persistence
                    try:
                        connection.rollback()
                    except DB_OPERATION_EXCEPTIONS as rb_e:
                        self.log.debug(
                            f"Rollback failed (non-critical, connection may be closed): {rb_e}"
                        )

                    error_str = str(e).lower()
                    if "sql0911n" in error_str or "timeout" in error_str or "deadlock" in error_str:
                        # Lock is held by another process, wait and retry
                        elapsed = int(time.time() - start_time)
                        self.log.debug(
                            f"Lock held by another process, waiting... (elapsed: {elapsed}s)"
                        )
                        time.sleep(1)
                        continue
                    elif "sql0803n" in error_str or "-803" in error_str or "duplicate" in error_str:
                        # Duplicate key - should not happen with MERGE, but handle gracefully
                        self.log.debug("Duplicate key error (unexpected with MERGE), retrying...")
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

        except DB_OPERATION_EXCEPTIONS as e:
            # Ensure transaction is rolled back in outer exception handler
            try:
                connection.rollback()
            except DB_OPERATION_EXCEPTIONS as rb_e:
                self.log.debug(f"Rollback failed (non-critical, connection may be closed): {rb_e}")

            error_msg = f"Error acquiring table-based migration lock for schema {schema}: {str(e)}"
            self.log.error(error_msg)
            return False

    def release_migration_lock(self, connection: Any, schema: str) -> bool:
        """Release the migration lock using DB2-specific unlock mechanisms.

        This method attempts to release locks acquired by any of the lock mechanisms:
        1. SYSTOOLS.LOCKING table
        2. Table-based locking

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name

        Returns:
            True if lock released, False otherwise
        """
        self.log.debug(f"Releasing migration lock in schema {schema}")

        # Track if we've successfully released any locks
        released = False

        # Try to clean up from SYSTOOLS.LOCKING if it was used
        if self._try_systools_locking_release(connection, schema):
            released = True

        # Clean up from our own lock table
        if self._try_table_based_locking_release(connection, schema):
            released = True

        return released

    def _try_systools_locking_release(self, connection: Any, schema: str) -> bool:
        """Try to release lock using SYSTOOLS.LOCKING table.

        Args:
            schema: Schema name

        Returns:
            True if lock released, False otherwise
        """
        try:
            check_systools_sql = """
            SELECT 1
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = 'SYSTOOLS'
            AND TABNAME = 'LOCKING'
            """

            systools_exists = (
                len(self.query_executor.execute_query(connection, check_systools_sql)) > 0
            )

            if systools_exists:
                # Generate the same lock ID used during acquisition
                lock_name = f"DBLIFT_MIGRATION_{schema.upper()}"

                # Delete our lock entry
                delete_lock_sql = """
                DELETE FROM SYSTOOLS.LOCKING
                WHERE NAME = ?
                """

                try:
                    affected = self.query_executor.execute_statement(
                        connection, delete_lock_sql, params=[lock_name]
                    )
                    connection.commit()

                    if affected > 0:
                        self.log.debug("Migration lock released via SYSTOOLS.LOCKING")
                        return True
                except DB_OPERATION_EXCEPTIONS as e:
                    connection.rollback()
                    self.log.debug(f"Error releasing lock via SYSTOOLS.LOCKING: {str(e)}")

            return False

        except DB_OPERATION_EXCEPTIONS as e:
            self.log.debug(f"SYSTOOLS.LOCKING table not available, error: {str(e)}")
            return False

    def _try_table_based_locking_release(self, connection: Any, schema: str) -> bool:
        """Try to release lock using table-based locking.

        Ensures proper transaction cleanup and always commits/rollbacks.

        Args:
            schema: Schema name

        Returns:
            True if lock released, False otherwise
        """
        try:
            # Ensure clean transaction state before release
            self._ensure_clean_transaction(connection)

            # Use database-specific default case for dblift objects
            from db.object_naming import get_normalized_object_name

            dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "db2")

            # First check if the lock table exists
            if not self.query_executor.table_exists(connection, schema, dblift_lock_table):
                # No lock table, nothing to release
                self.log.debug(f"Migration lock table does not exist in schema {schema}")
                return True

            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            # Delete the lock entry
            delete_sql = f"DELETE FROM {qualified_table} WHERE lock_name = 'migration'"

            try:
                affected = self.query_executor.execute_statement(connection, delete_sql)

                # CRITICAL: Explicitly commit the DELETE immediately (DB2 uses autoCommit=False)
                try:
                    connection.commit()
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.debug(f"Commit failed (non-critical, connection may be closed): {e}")

                if affected > 0:
                    self.log.debug("Migration lock released from lock table")

                    # Drop the lock table after release as requested; it will be recreated on next migration
                    try:
                        self._drop_lock_table_if_exists(connection, schema)
                    except DB_OPERATION_EXCEPTIONS as e:
                        self.log.debug(f"Non-fatal: could not drop lock table: {e}")
                    return True

                return False

            except DB_OPERATION_EXCEPTIONS:
                # CRITICAL: Always rollback on error
                try:
                    connection.rollback()
                except DB_OPERATION_EXCEPTIONS as rb_e:
                    self.log.debug(
                        f"Rollback failed (non-critical, connection may be closed): {rb_e}"
                    )
                raise

        except DB_OPERATION_EXCEPTIONS as e:
            # Ensure transaction is rolled back in outer exception handler
            try:
                connection.rollback()
            except DB_OPERATION_EXCEPTIONS as rb_e:
                self.log.debug(f"Rollback failed (non-critical, connection may be closed): {rb_e}")

            error_msg = f"Error releasing migration lock from lock table: {str(e)}"
            self.log.error(error_msg)
            return False

    def _get_drop_table_sql(self, qualified_table: str) -> str:
        """DB2 does not support DROP TABLE IF EXISTS — omit the IF EXISTS clause."""
        return f"DROP TABLE {qualified_table}"
