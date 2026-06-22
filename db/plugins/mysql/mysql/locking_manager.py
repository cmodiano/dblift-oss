"""
MySQL migration locking manager.

This module handles MySQL-specific migration locking functionality using
MySQL's GET_LOCK() and RELEASE_LOCK() functions for named locks.
"""

import os
import socket
from typing import Any, Optional

from core.logger import Log, NullLog
from db.object_naming import get_normalized_object_name
from db.plugins.base_locking_manager import BaseLockingManager


class MySqlLockingManager(BaseLockingManager):
    """Manages MySQL-specific migration locking using named locks."""

    # MySQL stores identifiers as-is (case-sensitive on Linux)
    DEFAULT_LOCK_TABLE = "dblift_migration_lock"
    MIGRATION_LOCK_TABLE = DEFAULT_LOCK_TABLE
    DIALECT = "mysql"

    def __init__(self, query_executor: Any, log: Optional[Log] = None) -> None:
        """Initialize the locking manager.

        Args:
            query_executor: Query executor instance
            log: Optional logger
        """
        self.query_executor: Any = query_executor
        self.log: Log = log if log is not None else NullLog()

    def create_migration_lock_table_if_not_exists(self, connection: Any, schema: str) -> None:
        """Create the migration lock table if it doesn't exist.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name (database name in MySQL)
        """
        self.log.debug(f"Checking migration lock table in schema {schema}")

        # Get database-specific case for dblift object
        dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "mysql")

        # Check if lock table exists
        if self.query_executor.table_exists(connection, schema, dblift_lock_table):
            self.log.debug(f"Migration lock table already exists in schema {schema}")
            return

        # Create lock table with MySQL-specific syntax
        qualified_table = self.query_executor.get_schema_qualified_name(schema, dblift_lock_table)
        create_table_sql = f"""
        CREATE TABLE {qualified_table} (
            lock_name VARCHAR(128) NOT NULL,
            acquired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acquired_by VARCHAR(128) NOT NULL,
            PRIMARY KEY (lock_name)
        ) ENGINE=InnoDB
        """

        try:
            self.query_executor.execute_statement(connection, create_table_sql)
            self.log.debug(f"Migration lock table created successfully in schema {schema}")
        except Exception as e:
            error_msg = f"Error creating migration lock table in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def acquire_migration_lock(
        self, connection: Any, schema: str, wait_timeout_seconds: int = 60
    ) -> bool:
        """Acquire a lock for migration operations using MySQL's GET_LOCK() function.

        MySQL provides named locks via GET_LOCK() which are session-based and
        automatically released when the connection is closed.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name (database name in MySQL)
            wait_timeout_seconds: Timeout in seconds to wait for lock

        Returns:
            True if lock acquired, False otherwise
        """
        self.log.debug(f"Attempting to acquire migration lock for schema {schema}")

        # Try MySQL's named lock mechanism first
        if self._try_named_lock_acquire(connection, schema, wait_timeout_seconds):
            return True

        # Fall back to table-based locking if named locks don't work
        return self._try_table_based_locking_acquire(connection, schema, wait_timeout_seconds)

    def _try_named_lock_acquire(
        self, connection: Any, schema: str, wait_timeout_seconds: int
    ) -> bool:
        """Try to acquire lock using MySQL's GET_LOCK() function.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            wait_timeout_seconds: Timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            # Create a unique lock name for this schema
            lock_name = f"dblift_migration_{schema}"

            # MySQL's GET_LOCK(name, timeout) returns:
            # 1 if lock was obtained successfully
            # 0 if the attempt timed out
            # NULL if an error occurred
            lock_sql = "SELECT GET_LOCK(?, ?) as lock_result"

            result = self.query_executor.execute_query(
                connection, lock_sql, params=[lock_name, wait_timeout_seconds]
            )

            if result and len(result) > 0:
                lock_result = result[0].get("lock_result")
                if lock_result == 1:
                    hostname = socket.gethostname()
                    username = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
                    process_id = os.getpid()
                    lock_identity = f"{username}@{hostname}:{process_id}"
                    self.log.debug(f"Migration lock acquired via GET_LOCK by {lock_identity}")
                    return True
                elif lock_result == 0:
                    self.log.debug(f"Failed to acquire lock within {wait_timeout_seconds} seconds")
                    return False
                else:  # NULL - error occurred
                    self.log.debug(
                        "GET_LOCK returned NULL (error), falling back to table-based locking"
                    )
                    return False

            return False

        except Exception as e:
            self.log.debug(f"MySQL GET_LOCK function failed, error: {str(e)}")
            return False

    def _try_table_based_locking_acquire(
        self, connection: Any, schema: str, wait_timeout_seconds: int
    ) -> bool:
        """Try to acquire lock using table-based locking mechanism.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name
            wait_timeout_seconds: Timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        self.log.debug("Using table-based locking mechanism")

        # Create lock table if it doesn't exist
        self.create_migration_lock_table_if_not_exists(connection, schema)

        try:
            # Use MySQL's SELECT ... FOR UPDATE with timeout
            # First check if lock exists
            dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "mysql")
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )
            check_sql = f"""
            SELECT lock_name, acquired_at, acquired_by
            FROM {qualified_table}
            WHERE lock_name = 'migration'
            FOR UPDATE
            """

            # Set innodb_lock_wait_timeout for this session
            timeout_sql = f"SET SESSION innodb_lock_wait_timeout = {wait_timeout_seconds}"
            self.query_executor.execute_statement(connection, timeout_sql)

            try:
                lock_rows = self.query_executor.execute_query(connection, check_sql)

                hostname = socket.gethostname()
                username = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
                process_id = os.getpid()
                lock_identity = f"{username}@{hostname}:{process_id}"

                if lock_rows and len(lock_rows) > 0:
                    # Lock exists, update it
                    dblift_lock_table = get_normalized_object_name(
                        self.MIGRATION_LOCK_TABLE, "mysql"
                    )
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, dblift_lock_table
                    )
                    update_sql = f"""
                    UPDATE {qualified_table}
                    SET acquired_at = CURRENT_TIMESTAMP, acquired_by = ?
                    WHERE lock_name = 'migration'
                    """

                    self.query_executor.execute_statement(
                        connection, update_sql, params=[lock_identity]
                    )

                    self.log.debug(f"Migration lock acquired via table update by {lock_identity}")
                    return True
                else:
                    # No lock exists, insert a new one
                    dblift_lock_table = get_normalized_object_name(
                        self.MIGRATION_LOCK_TABLE, "mysql"
                    )
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, dblift_lock_table
                    )
                    insert_sql = f"""
                    INSERT INTO {qualified_table} (
                        lock_name, acquired_at, acquired_by
                    ) VALUES (
                        'migration', CURRENT_TIMESTAMP, ?
                    )
                    """

                    self.query_executor.execute_statement(
                        connection, insert_sql, params=[lock_identity]
                    )

                    self.log.debug(f"Migration lock acquired via table insert by {lock_identity}")
                    return True

            except Exception as e:
                if "lock wait timeout exceeded" in str(e).lower():
                    self.log.error(f"Lock wait timeout exceeded: {str(e)}")
                    return False
                elif "duplicate entry" in str(e).lower():
                    # Race condition: another process inserted the lock between our SELECT and INSERT
                    # This means another process has already acquired the lock
                    # We should not try to update it as that would break mutual exclusion
                    self.log.debug(
                        f"Migration lock already acquired by another process. "
                        f"Race condition detected, failing lock acquisition by {lock_identity}"
                    )
                    return False
                raise

        except Exception as e:
            error_msg = f"Error acquiring migration lock: {str(e)}"
            self.log.error(error_msg)
            return False
        finally:
            # Reset lock wait timeout to default
            try:
                self.query_executor.execute_statement(
                    connection, "SET SESSION innodb_lock_wait_timeout = DEFAULT"
                )
            except Exception:
                pass

    def release_migration_lock(self, connection: Any, schema: str) -> bool:
        """Release the migration lock using MySQL-specific unlock mechanisms.

        This method attempts to release locks acquired by either:
        1. MySQL's GET_LOCK() function
        2. Table-based locking

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name

        Returns:
            True if lock released, False otherwise
        """
        self.log.debug(f"Releasing migration lock for schema {schema}")

        # Track if we've successfully released any locks
        released = False

        # Try to release named lock first
        if self._try_named_lock_release(connection, schema):
            released = True

        # Also try to clean up table-based lock
        if self._try_table_based_locking_release(connection, schema):
            released = True

        return released

    def _try_named_lock_release(self, connection: Any, schema: str) -> bool:
        """Try to release lock using MySQL's RELEASE_LOCK() function.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name

        Returns:
            True if lock released, False otherwise
        """
        try:
            # Create the same lock name used during acquisition
            lock_name = f"dblift_migration_{schema}"

            # MySQL's RELEASE_LOCK(name) returns:
            # 1 if the lock was released
            # 0 if the lock was not established by this thread (released by someone else)
            # NULL if the named lock did not exist
            unlock_sql = "SELECT RELEASE_LOCK(?) as unlock_result"

            result = self.query_executor.execute_query(connection, unlock_sql, params=[lock_name])

            if result and len(result) > 0:
                unlock_result = result[0].get("unlock_result")
                if unlock_result == 1:
                    self.log.debug("Migration lock released via RELEASE_LOCK")
                    return True
                elif unlock_result == 0:
                    self.log.debug("Lock was not established by this thread")
                    return False
                else:  # NULL - lock did not exist
                    self.log.debug("Named lock did not exist")
                    return False

            return False

        except Exception as e:
            self.log.debug(f"MySQL RELEASE_LOCK function failed, error: {str(e)}")
            return False

    def _try_table_based_locking_release(self, connection: Any, schema: str) -> bool:
        """Try to release lock using table-based locking.

        Args:
            connection: Active database connection (provided by Provider)
            schema: Schema name

        Returns:
            True if lock released, False otherwise
        """
        try:
            # First check if the lock table exists
            dblift_lock_table = get_normalized_object_name(self.MIGRATION_LOCK_TABLE, "mysql")
            if not self.query_executor.table_exists(connection, schema, dblift_lock_table):
                self.log.debug(f"Migration lock table does not exist in schema {schema}")
                return True

            # Delete the lock entry
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )
            delete_sql = f"""
            DELETE FROM {qualified_table}
            WHERE lock_name = 'migration'
            """

            affected = self.query_executor.execute_statement(connection, delete_sql)

            if affected > 0:
                self.log.debug("Migration lock released from lock table")

                # Drop the lock table since it was only used as fallback
                self._drop_lock_table_if_exists(connection, schema)
                return True

            return False

        except Exception as e:
            error_msg = f"Error releasing migration lock from lock table: {str(e)}"
            self.log.error(error_msg)
            return False
