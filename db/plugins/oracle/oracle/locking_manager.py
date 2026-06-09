"""
Oracle migration locking manager.

This module handles Oracle-specific migration locking using Oracle's DBMS_LOCK package
to ensure only one migration process can run at a time per schema.
"""

import os
import time
from typing import Any, Dict, Optional

from core.logger import Log, NullLog
from db.object_naming import get_normalized_object_name
from db.plugins.base_locking_manager import BaseLockingManager


class OracleLockingManager(BaseLockingManager):
    """Manages Oracle migration locking operations."""

    # Lock modes from Oracle DBMS_LOCK package
    LOCK_X_MODE = 6  # eXclusive mode

    # Oracle stores unquoted identifiers as UPPERCASE
    DEFAULT_LOCK_TABLE = "DBLIFT_MIGRATION_LOCK"
    MIGRATION_LOCK = DEFAULT_LOCK_TABLE
    DIALECT = "oracle"
    LOCK_PREFIX = "DBLIFT_MIG_LOCK_"
    LOCK_NAME_MAXLEN = 30  # Oracle's safe identifier length

    def __init__(
        self, query_executor: Any, log: Optional[Log] = None, provider: Any = None
    ) -> None:
        """Initialize the locking manager.

        Args:
            query_executor: Query executor instance for database operations
            log: Optional logger
            provider: Optional provider instance for transaction management
        """
        self.query_executor = query_executor
        self.log = log if log is not None else NullLog()
        self.provider = provider
        self._lock_handles: Dict[str, Any] = {}

    @staticmethod
    def get_lock_name(schema: str) -> str:
        """Get the lock name for a schema.

        Oracle has a 30 character limit for identifiers in DBMS_LOCK.
        We use uppercase for the lock name to match Oracle's default convention.
        """
        # Oracle has a 30 character limit for identifiers
        prefix = "DBLIFT_MIG_LOCK_"
        max_schema_len = 30 - len(prefix)
        # Remove quotes if present
        clean_schema = schema.replace('"', "").strip()
        schema_upper = clean_schema.upper()
        if len(schema_upper) > max_schema_len:
            schema_upper = schema_upper[:max_schema_len]
        return f"{prefix}{schema_upper}"

    @classmethod
    def get_lock_key(cls, schema: str) -> str:
        """Return the key used for storing the lock handle (same as lock name)."""
        return cls.get_lock_name(schema)

    def create_migration_lock_table_if_not_exists(self, connection: Any, schema: str) -> None:
        """Create the migration lock table if it doesn't exist.

        This table is used to track active migration locks and prevent
        concurrent migrations on the same schema.

        Args:
            schema: Target schema name
        """
        self.log.debug(f"Creating migration lock table if not exists in schema: {schema}")

        try:
            # Use Oracle's default case (UPPERCASE) for dblift objects
            dblift_lock_table = get_normalized_object_name("DBLIFT_MIGRATION_LOCK", "oracle")
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )

            create_table_sql = f"""
            CREATE TABLE {qualified_table} (
                LOCK_NAME VARCHAR2(128) NOT NULL PRIMARY KEY,
                ACQUIRED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                ACQUIRED_BY VARCHAR2(256) DEFAULT USER NOT NULL,
                SESSION_ID NUMBER DEFAULT SYS_CONTEXT('USERENV','SID') NOT NULL,
                PROCESS_ID VARCHAR2(64),
                LOCK_MODE NUMBER DEFAULT {self.LOCK_X_MODE} NOT NULL
            )
            """

            # Check if table already exists first
            if not self.query_executor.table_exists(connection, schema, dblift_lock_table):
                self.query_executor.execute_statement(connection, create_table_sql)
                self.log.debug(f"Created migration lock table in schema: {schema}")
            else:
                self.log.debug(f"Migration lock table already exists in schema: {schema}")

        except Exception as e:
            # If table already exists, that's fine
            # Check for Oracle error code ORA-00955 (name is already used by an existing object)
            # which is locale-independent
            error_str = str(e).lower()
            if (
                "already exists" in error_str
                or "name is already used" in error_str
                or "ora-00955" in error_str
                or "existe déjà" in error_str  # French: already exists
                or "existe já" in error_str
            ):  # Portuguese: already exists
                self.log.debug(f"Migration lock table already exists in schema: {schema}")
            else:
                error_msg = f"Error creating migration lock table in schema {schema}: {str(e)}"
                self.log.error(error_msg)
                raise

    def acquire_migration_lock(
        self, connection: Any, schema: str, wait_timeout_seconds: int = 60
    ) -> bool:
        """Acquire an exclusive migration lock for the specified schema.

        Uses Oracle's DBMS_LOCK package to create an application-level lock
        that prevents concurrent migrations on the same schema. Falls back to
        table-based locking if DBMS_LOCK is not available.

        Args:
            schema: Target schema name
            wait_timeout_seconds: Maximum time to wait for lock acquisition

        Returns:
            bool: True if lock was acquired successfully, False otherwise
        """
        self.log.debug(f"Attempting to acquire migration lock for schema: {schema}")

        try:
            # Get the lock name for this schema
            lock_name = self.get_lock_name(schema)
            lock_key = self.get_lock_key(schema)

            self.log.debug(f"Using lock name: {lock_name}")

            # First, try to allocate a lock handle using DBMS_LOCK.ALLOCATE_UNIQUE.
            # Suppress query-executor error logging for this probe: DBMS_LOCK is
            # unavailable on many Oracle installations (requires DBA grant), so
            # ORA-06550 here is expected and handled by the table-based fallback.
            # We log at debug level ourselves below; surfacing it as ERROR would
            # alarm users before the migration log header has opened.
            allocate_sql = """
            DECLARE
                lock_handle VARCHAR2(128);
            BEGIN
                DBMS_LOCK.ALLOCATE_UNIQUE(?, lock_handle);
            END;
            """

            try:
                self.query_executor.execute_statement(
                    connection, allocate_sql, params=[lock_name], silent=True
                )
            except Exception:
                self.log.debug("DBMS_LOCK not accessible; will fall back to table-based locking")

            # Get a unique handle for this lock
            handle_sql = "SELECT DBMS_UTILITY.GET_HASH_VALUE(?, 0, 1073741823) as hash FROM DUAL"
            hash_result = self.query_executor.execute_query(
                connection, handle_sql, params=[lock_name]
            )

            if hash_result and len(hash_result) > 0:
                lock_handle = hash_result[0].get("hash", hash_result[0].get("HASH"))
            else:
                # Fallback: use a deterministic hash of the lock name
                lock_handle = hash(lock_name) & 0x7FFFFFFF  # Ensure positive 32-bit integer

            self.log.debug(f"Using lock handle: {lock_handle}")

            # Store the handle for later release
            self._lock_handles[lock_key] = lock_handle

            # Now try to acquire the lock using native DBMS_LOCK
            start_time = time.time()
            max_wait_time = wait_timeout_seconds

            used_dbms_lock = True
            while time.time() - start_time < max_wait_time:
                try:
                    # Try to acquire the lock with a short timeout.
                    # Suppress query-executor error logging for the same reason as the
                    # ALLOCATE_UNIQUE probe: ORA-00904 here is expected when the user
                    # lacks EXECUTE on DBMS_LOCK; the warning is emitted at line 223 by
                    # the locking manager itself, inside the migration log.
                    acquire_sql = "SELECT DBMS_LOCK.REQUEST(?, ?, ?) as result FROM DUAL"
                    lock_result = self.query_executor.execute_query(
                        connection,
                        acquire_sql,
                        params=[
                            lock_handle,
                            self.LOCK_X_MODE,
                            5,
                        ],  # 5 second timeout per attempt
                        silent=True,
                    )

                    if lock_result and len(lock_result) > 0:
                        result_code = lock_result[0].get("result", lock_result[0].get("RESULT", -1))

                        if result_code == 0:
                            # Lock acquired successfully using native DBMS_LOCK
                            self.log.debug(
                                f"Successfully acquired migration lock for schema: {schema} using native DBMS_LOCK"
                            )
                            return True
                        elif result_code == 1:
                            # Lock timeout - try again
                            self.log.debug(
                                f"Lock timeout, retrying... (elapsed: {int(time.time() - start_time)}s)"
                            )
                            time.sleep(1)
                            continue
                        elif result_code == 4:
                            # Already own lock
                            self.log.debug(f"Already own migration lock for schema: {schema}")
                            return True
                        else:
                            # Other error - fall back to table-based locking
                            used_dbms_lock = False
                            self.log.debug(
                                f"DBMS_LOCK request failed with code {result_code}; falling back to table-based locking"
                            )
                            break
                    else:
                        self.log.debug("No result returned from lock request; falling back")
                        used_dbms_lock = False
                        break

                except Exception as e:
                    self.log.debug(f"DBMS_LOCK acquisition error: {str(e)}; falling back")
                    used_dbms_lock = False
                    break

            # If DBMS_LOCK path didn't succeed, try table-based locking
            if not used_dbms_lock:
                # Clean up the unused DBMS_LOCK handle before falling back
                if lock_key in self._lock_handles:
                    del self._lock_handles[lock_key]
                self.log.debug("Falling back to table-based locking mechanism")
                return self._acquire_table_based_lock(
                    connection, schema, lock_name, lock_key, wait_timeout_seconds
                )

            # If we were using DBMS_LOCK and reached here, timeout exceeded
            # Clean up the unused lock handle to prevent memory leak
            if lock_key in self._lock_handles:
                del self._lock_handles[lock_key]
            self.log.warning(
                f"Failed to acquire migration lock for schema {schema} within {wait_timeout_seconds} seconds"
            )
            return False

        except Exception as e:
            # Clean up the unused lock handle before falling back
            lock_name = self.get_lock_name(schema)
            lock_key = self.get_lock_key(schema)
            if lock_key in self._lock_handles:
                del self._lock_handles[lock_key]
            self.log.warning(
                f"Error acquiring native migration lock for schema {schema}: {str(e)}; falling back to table-based locking"
            )
            # Fall back to table-based locking
            return self._acquire_table_based_lock(
                connection, schema, lock_name, lock_key, wait_timeout_seconds
            )

    def _acquire_table_based_lock(
        self,
        connection: Any,
        schema: str,
        lock_name: str,
        lock_key: str,
        wait_timeout_seconds: int,
    ) -> bool:
        """Acquire lock using table-based mechanism as fallback.

        Args:
            schema: Target schema name
            lock_name: Lock name for this schema
            lock_key: Lock key for handle storage
            wait_timeout_seconds: Maximum time to wait for lock acquisition

        Returns:
            bool: True if lock was acquired successfully, False otherwise
        """
        self.log.debug("Using table-based locking mechanism as fallback")

        try:
            # Create lock table if it doesn't exist (only needed for fallback)
            self.create_migration_lock_table_if_not_exists(connection, schema)

            # Use Oracle's default case (UPPERCASE) for dblift objects
            dblift_lock_table = get_normalized_object_name("DBLIFT_MIGRATION_LOCK", "oracle")
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )
            start_time = time.time()
            process_id = str(os.getpid())
            while time.time() - start_time < wait_timeout_seconds:
                try:
                    insert_sql = f"""
                    INSERT INTO {qualified_table}
                    (LOCK_NAME, ACQUIRED_AT, ACQUIRED_BY, SESSION_ID, PROCESS_ID, LOCK_MODE)
                    VALUES (?, CURRENT_TIMESTAMP, USER, SYS_CONTEXT('USERENV','SID'), ?, ?)
                    """
                    self.query_executor.execute_statement(
                        connection, insert_sql, params=[lock_name, process_id, self.LOCK_X_MODE]
                    )
                    self.log.debug(f"Acquired table-based migration lock for schema: {schema}")
                    # Mark that no DBMS_LOCK handle was used
                    self._lock_handles[lock_key] = None
                    return True
                except Exception as e:
                    msg = str(e).lower()
                    if "unique" in msg or "ora-00001" in msg or "integrity" in msg:
                        # Someone else holds the lock; wait and retry
                        elapsed = int(time.time() - start_time)
                        self.log.debug(
                            f"Lock held by another process, waiting... (elapsed: {elapsed}s)"
                        )
                        time.sleep(1)
                        continue
                    else:
                        self.log.warning(
                            f"Table-based lock insert failed with non-retryable error: {e}"
                        )
                        return False

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

        Tries to release native DBMS_LOCK first, then cleans up table-based lock if it exists.

        Args:
            schema: Target schema name

        Returns:
            bool: True if lock was released successfully, False otherwise
        """
        self.log.debug(f"Attempting to release migration lock for schema: {schema}")

        released = False

        try:
            lock_name = self.get_lock_name(schema)
            lock_key = self.get_lock_key(schema)

            # Get the stored lock handle (None means fallback/table-only lock)
            lock_handle = self._lock_handles.get(lock_key)

            # If we have a DBMS_LOCK handle, try to release it
            if lock_handle is not None:
                try:
                    release_sql = "SELECT DBMS_LOCK.RELEASE(?) as result FROM DUAL"
                    result = self.query_executor.execute_query(
                        connection, release_sql, params=[lock_handle]
                    )
                    if result and len(result) > 0:
                        result_code = result[0].get("result", result[0].get("RESULT", -1))
                        if result_code == 0:
                            self.log.debug(
                                f"Successfully released native DBMS_LOCK for schema: {schema}"
                            )
                            released = True
                        else:
                            self.log.debug(
                                f"DBMS_LOCK release returned code: {result_code} (may not have been held)"
                            )
                except Exception as e:
                    self.log.debug(f"Could not release native DBMS_LOCK: {str(e)}")

            # Also try to clean up table-based lock (if it was used as fallback)
            try:
                # Use Oracle's default case (UPPERCASE) for dblift objects
                dblift_lock_table = get_normalized_object_name("DBLIFT_MIGRATION_LOCK", "oracle")
                if self.query_executor.table_exists(connection, schema, dblift_lock_table):
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, dblift_lock_table
                    )
                    delete_sql = f"DELETE FROM {qualified_table} WHERE LOCK_NAME = ?"
                    rows = self.query_executor.execute_statement(
                        connection, delete_sql, params=[lock_name]
                    )
                    # Commit the DELETE to ensure lock is released even if connection is reused
                    # This is critical for Oracle with autoCommit=False
                    if self.provider and hasattr(self.provider, "commit_transaction"):
                        try:
                            self.provider.commit_transaction()
                            self.log.debug("Lock release committed successfully")
                        except Exception as commit_err:
                            self.log.debug(f"Lock release commit error (non-fatal): {commit_err}")

                    if rows > 0:
                        self.log.debug(f"Cleaned up table-based lock record for schema: {schema}")
                        released = True

                        # Drop the lock table since it was only used as fallback
                        self._drop_lock_table_if_exists(connection, schema)
            except Exception as e:
                self.log.debug(f"Could not clean up table-based lock: {str(e)}")

            # Cleanup handle
            if lock_key in self._lock_handles:
                del self._lock_handles[lock_key]

            return released

        except Exception as e:
            error_msg = f"Error releasing migration lock for schema {schema}: {str(e)}"
            self.log.error(error_msg)
            return False

    def _get_drop_table_sql(self, qualified_table: str) -> str:
        """Oracle does not support DROP TABLE IF EXISTS — omit the IF EXISTS clause."""
        return f"DROP TABLE {qualified_table}"
