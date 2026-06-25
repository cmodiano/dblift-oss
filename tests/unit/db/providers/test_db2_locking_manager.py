"""Unit tests for DB2 locking manager.

Covers Db2LockingManager (db/plugins/db2/db2/locking_manager.py):
- create_migration_lock_table_if_not_exists
- acquire_migration_lock (systools + table-based paths)
- release_migration_lock (systools + table-based paths)
- helper methods: _ensure_clean_transaction, _cleanup_stale_locks,
  _try_systools_locking_acquire, _try_systools_locking_release,
  _try_table_based_locking_acquire, _try_table_based_locking_release

JDBC mock pattern: conn = MagicMock(), conn.isClosed.return_value = False,
conn.getAutoCommit.return_value = False.
"""

import unittest
from unittest.mock import MagicMock, call, patch


def _make_connection(auto_commit=False):
    conn = MagicMock()
    conn.isClosed.return_value = False
    conn.getAutoCommit.return_value = auto_commit
    return conn


def _make_qe():
    qe = MagicMock()
    qe.execute_query.return_value = []
    qe.execute_statement.return_value = 0
    qe.table_exists.return_value = False
    qe.get_schema_qualified_name.side_effect = lambda s, n: f'"{s}"."{n}"'
    return qe


def _make_manager(qe=None, log=None):
    from db.plugins.db2.db2.locking_manager import Db2LockingManager

    if qe is None:
        qe = _make_qe()
    if log is None:
        log = MagicMock()
    return Db2LockingManager(qe, log), qe, log


# ---------------------------------------------------------------------------
# Constructor / NullLog
# ---------------------------------------------------------------------------


class TestDb2LockingManagerInit(unittest.TestCase):

    def test_uses_nulllog_when_no_log_provided(self):
        from core.logger import NullLog
        from db.plugins.db2.db2.locking_manager import Db2LockingManager

        qe = _make_qe()
        manager = Db2LockingManager(qe)
        self.assertIsInstance(manager.log, NullLog)

    def test_uses_provided_log(self):
        qe = _make_qe()
        log = MagicMock()
        manager, _, stored_log = _make_manager(qe=qe, log=log)
        self.assertIs(stored_log, manager.log)

    def test_default_lock_table_is_uppercase(self):
        from db.plugins.db2.db2.locking_manager import Db2LockingManager

        self.assertEqual("DBLIFT_MIGRATION_LOCK", Db2LockingManager.DEFAULT_LOCK_TABLE)

    def test_dialect_is_db2(self):
        from db.plugins.db2.db2.locking_manager import Db2LockingManager

        self.assertEqual("db2", Db2LockingManager.DIALECT)


# ---------------------------------------------------------------------------
# create_migration_lock_table_if_not_exists
# ---------------------------------------------------------------------------


class TestDb2CreateLockTable(unittest.TestCase):

    def test_skips_when_table_already_exists(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        manager.create_migration_lock_table_if_not_exists(conn, "MYSCHEMA")
        qe.execute_statement.assert_not_called()

    def test_creates_table_when_missing(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        manager.create_migration_lock_table_if_not_exists(conn, "MYSCHEMA")
        qe.execute_statement.assert_called_once()
        sql = qe.execute_statement.call_args[0][1]
        self.assertIn("CREATE TABLE", sql)

    def test_creates_table_with_required_columns(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        manager.create_migration_lock_table_if_not_exists(conn, "MYSCHEMA")
        sql = qe.execute_statement.call_args[0][1]
        self.assertIn("lock_name", sql)
        self.assertIn("acquired_at", sql)
        self.assertIn("acquired_by", sql)

    def test_commits_after_create(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        manager.create_migration_lock_table_if_not_exists(conn, "MYSCHEMA")
        conn.commit.assert_called()

    def test_raises_on_create_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        qe.execute_statement.side_effect = RuntimeError("table already exists")
        with self.assertRaises(RuntimeError):
            manager.create_migration_lock_table_if_not_exists(conn, "MYSCHEMA")

    def test_rolls_back_on_create_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        qe.execute_statement.side_effect = RuntimeError("create failed")
        try:
            manager.create_migration_lock_table_if_not_exists(conn, "MYSCHEMA")
        except RuntimeError:
            pass
        conn.rollback.assert_called()


# ---------------------------------------------------------------------------
# _ensure_clean_transaction
# ---------------------------------------------------------------------------


class TestDb2EnsureCleanTransaction(unittest.TestCase):

    def test_rollback_when_autocommit_false(self):
        manager, qe, log = _make_manager()
        conn = _make_connection(auto_commit=False)
        manager._ensure_clean_transaction(conn)
        conn.rollback.assert_called_once()

    def test_no_rollback_when_autocommit_true(self):
        manager, qe, log = _make_manager()
        conn = _make_connection(auto_commit=True)
        manager._ensure_clean_transaction(conn)
        conn.rollback.assert_not_called()

    def test_handles_exception_gracefully(self):
        manager, qe, log = _make_manager()
        conn = _make_connection(auto_commit=False)
        conn.rollback.side_effect = RuntimeError("rollback failed")
        # Should not raise
        manager._ensure_clean_transaction(conn)


# ---------------------------------------------------------------------------
# _cleanup_stale_locks
# ---------------------------------------------------------------------------


class TestDb2CleanupStaleLocks(unittest.TestCase):

    def test_skips_when_table_does_not_exist(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        manager._cleanup_stale_locks(conn, "MYSCHEMA", 60)
        qe.execute_statement.assert_not_called()

    def test_executes_delete_when_table_exists(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.return_value = 0
        manager._cleanup_stale_locks(conn, "MYSCHEMA", 60)
        qe.execute_statement.assert_called()
        sql = qe.execute_statement.call_args[0][1]
        self.assertIn("DELETE", sql)

    def test_commits_after_cleanup(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.return_value = 2
        manager._cleanup_stale_locks(conn, "MYSCHEMA", 60)
        conn.commit.assert_called()

    def test_handles_sql204_error_silently(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.side_effect = RuntimeError("SQL204N table not found -204")
        # Should not raise (SQL-204 = table doesn't exist)
        manager._cleanup_stale_locks(conn, "MYSCHEMA", 60)

    def test_rolls_back_on_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.side_effect = RuntimeError("some error")
        manager._cleanup_stale_locks(conn, "MYSCHEMA", 60)
        conn.rollback.assert_called()


# ---------------------------------------------------------------------------
# _try_systools_locking_acquire
# ---------------------------------------------------------------------------


class TestDb2SystoolsLockingAcquire(unittest.TestCase):

    def test_returns_false_when_systools_not_available(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = []  # SYSTOOLS.LOCKING not found
        result = manager._try_systools_locking_acquire(conn, "MYSCHEMA", 60)
        self.assertFalse(result)

    def test_returns_true_when_lock_inserted_successfully(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        # First query: systools check returns 1 row
        qe.execute_query.return_value = [{"1": 1}]
        qe.execute_statement.return_value = 0
        result = manager._try_systools_locking_acquire(conn, "MYSCHEMA", 60)
        self.assertTrue(result)

    def test_commits_after_successful_insert(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = [{"1": 1}]
        qe.execute_statement.return_value = 0
        manager._try_systools_locking_acquire(conn, "MYSCHEMA", 60)
        conn.commit.assert_called()

    def test_returns_false_on_insert_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = [{"1": 1}]
        # First execute_statement = cleanup (ok), second = insert (fails)
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                raise RuntimeError("duplicate key")
            return 0

        qe.execute_statement.side_effect = side_effect
        result = manager._try_systools_locking_acquire(conn, "MYSCHEMA", 60)
        self.assertFalse(result)
        conn.rollback.assert_called()

    def test_returns_false_on_outer_exception(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.side_effect = RuntimeError("syscat not available")
        result = manager._try_systools_locking_acquire(conn, "MYSCHEMA", 60)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _try_table_based_locking_acquire
# ---------------------------------------------------------------------------


class TestDb2TableBasedLockingAcquire(unittest.TestCase):

    def test_returns_true_on_successful_merge(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.return_value = 1
        with patch("time.time", side_effect=[0, 0.1]):
            result = manager._try_table_based_locking_acquire(conn, "MYSCHEMA", 5)
        self.assertTrue(result)
        conn.commit.assert_called()

    def test_returns_false_on_timeout(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        # Always raise timeout error to force timeout path
        qe.execute_statement.side_effect = RuntimeError("sql0911n timeout")
        import time as _time

        # Use real time to test timeout quickly with wait_timeout_seconds=0
        result = manager._try_table_based_locking_acquire(conn, "MYSCHEMA", 0)
        self.assertFalse(result)

    def test_rolls_back_on_merge_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.side_effect = RuntimeError("sql0911n timeout")
        manager._try_table_based_locking_acquire(conn, "MYSCHEMA", 0)
        conn.rollback.assert_called()

    def test_creates_lock_table_if_missing(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        # table_exists calls in order:
        #   1) create_migration_lock_table_if_not_exists -> False (missing, triggers CREATE)
        #   2) _try_table_based_locking_acquire pre-cleanup probe -> True (now exists)
        #   3) _cleanup_stale_locks inner check -> True (still exists)
        qe.table_exists.side_effect = [False, True, True]
        qe.execute_statement.return_value = 1
        with patch("time.time", side_effect=[0, 0.1]):
            manager._try_table_based_locking_acquire(conn, "MYSCHEMA", 5)
        # execute_statement called: CREATE TABLE + MERGE
        self.assertTrue(qe.execute_statement.call_count >= 1)

    def test_duplicate_key_error_retried(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RuntimeError("sql0803n duplicate key")
            return 1

        qe.execute_statement.side_effect = side_effect
        with patch("time.sleep"):
            with patch("time.time", side_effect=[0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6]):
                result = manager._try_table_based_locking_acquire(conn, "MYSCHEMA", 10)
        # After retrying, eventually succeeds
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# acquire_migration_lock (integration of strategies)
# ---------------------------------------------------------------------------


class TestDb2AcquireMigrationLock(unittest.TestCase):

    def test_uses_systools_when_available(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_acquire", return_value=True) as mock_sys:
            result = manager.acquire_migration_lock(conn, "MYSCHEMA")
        self.assertTrue(result)
        mock_sys.assert_called_once()

    def test_falls_back_to_table_when_systools_unavailable(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_acquire", return_value=False):
            with patch.object(
                manager, "_try_table_based_locking_acquire", return_value=True
            ) as mock_tbl:
                result = manager.acquire_migration_lock(conn, "MYSCHEMA")
        self.assertTrue(result)
        mock_tbl.assert_called_once()

    def test_returns_false_when_all_mechanisms_fail(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_acquire", return_value=False):
            with patch.object(manager, "_try_table_based_locking_acquire", return_value=False):
                result = manager.acquire_migration_lock(conn, "MYSCHEMA")
        self.assertFalse(result)

    def test_logs_error_when_all_fail(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_acquire", return_value=False):
            with patch.object(manager, "_try_table_based_locking_acquire", return_value=False):
                manager.acquire_migration_lock(conn, "MYSCHEMA")
        log.error.assert_called()


# ---------------------------------------------------------------------------
# _try_systools_locking_release
# ---------------------------------------------------------------------------


class TestDb2SystoolsLockingRelease(unittest.TestCase):

    def test_returns_false_when_systools_not_available(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = []
        result = manager._try_systools_locking_release(conn, "MYSCHEMA")
        self.assertFalse(result)

    def test_returns_true_when_lock_deleted(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = [{"1": 1}]
        qe.execute_statement.return_value = 1  # 1 row deleted
        result = manager._try_systools_locking_release(conn, "MYSCHEMA")
        self.assertTrue(result)
        conn.commit.assert_called()

    def test_returns_false_when_no_row_deleted(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = [{"1": 1}]
        qe.execute_statement.return_value = 0
        result = manager._try_systools_locking_release(conn, "MYSCHEMA")
        self.assertFalse(result)

    def test_returns_false_on_delete_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.return_value = [{"1": 1}]
        qe.execute_statement.side_effect = RuntimeError("delete failed")
        result = manager._try_systools_locking_release(conn, "MYSCHEMA")
        self.assertFalse(result)
        conn.rollback.assert_called()

    def test_returns_false_on_outer_exception(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.execute_query.side_effect = RuntimeError("syscat not available")
        result = manager._try_systools_locking_release(conn, "MYSCHEMA")
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _try_table_based_locking_release
# ---------------------------------------------------------------------------


class TestDb2TableBasedLockingRelease(unittest.TestCase):

    def test_returns_true_when_no_lock_table(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = False
        result = manager._try_table_based_locking_release(conn, "MYSCHEMA")
        self.assertTrue(result)

    def test_returns_true_when_row_deleted(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.return_value = 1
        with patch.object(manager, "_drop_lock_table_if_exists"):
            result = manager._try_table_based_locking_release(conn, "MYSCHEMA")
        self.assertTrue(result)
        conn.commit.assert_called()

    def test_returns_false_when_no_row_deleted(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.return_value = 0
        result = manager._try_table_based_locking_release(conn, "MYSCHEMA")
        self.assertFalse(result)

    def test_drops_lock_table_after_successful_delete(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.return_value = 1
        with patch.object(manager, "_drop_lock_table_if_exists") as mock_drop:
            manager._try_table_based_locking_release(conn, "MYSCHEMA")
        mock_drop.assert_called_once()

    def test_rolls_back_and_returns_false_on_delete_error(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.side_effect = RuntimeError("delete failed")
        result = manager._try_table_based_locking_release(conn, "MYSCHEMA")
        self.assertFalse(result)
        conn.rollback.assert_called()

    def test_logs_error_message_on_failure(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        qe.table_exists.return_value = True
        qe.execute_statement.side_effect = RuntimeError("delete failed")
        manager._try_table_based_locking_release(conn, "MYSCHEMA")
        log.error.assert_called()


# ---------------------------------------------------------------------------
# release_migration_lock (integration)
# ---------------------------------------------------------------------------


class TestDb2ReleaseMigrationLock(unittest.TestCase):

    def test_returns_true_when_systools_release_succeeds(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_release", return_value=True):
            with patch.object(manager, "_try_table_based_locking_release", return_value=False):
                result = manager.release_migration_lock(conn, "MYSCHEMA")
        self.assertTrue(result)

    def test_returns_true_when_table_release_succeeds(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_release", return_value=False):
            with patch.object(manager, "_try_table_based_locking_release", return_value=True):
                result = manager.release_migration_lock(conn, "MYSCHEMA")
        self.assertTrue(result)

    def test_returns_false_when_both_fail(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_release", return_value=False):
            with patch.object(manager, "_try_table_based_locking_release", return_value=False):
                result = manager.release_migration_lock(conn, "MYSCHEMA")
        self.assertFalse(result)

    def test_both_mechanisms_attempted(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_release", return_value=True) as mock_sys:
            with patch.object(
                manager, "_try_table_based_locking_release", return_value=True
            ) as mock_tbl:
                manager.release_migration_lock(conn, "MYSCHEMA")
        mock_sys.assert_called_once()
        mock_tbl.assert_called_once()

    def test_returns_true_when_both_succeed(self):
        manager, qe, log = _make_manager()
        conn = _make_connection()
        with patch.object(manager, "_try_systools_locking_release", return_value=True):
            with patch.object(manager, "_try_table_based_locking_release", return_value=True):
                result = manager.release_migration_lock(conn, "MYSCHEMA")
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# _get_drop_table_sql
# ---------------------------------------------------------------------------


class TestDb2GetDropTableSql(unittest.TestCase):

    def test_omits_if_exists_clause(self):
        manager, qe, log = _make_manager()
        sql = manager._get_drop_table_sql('"MYSCHEMA"."DBLIFT_MIGRATION_LOCK"')
        self.assertIn("DROP TABLE", sql)
        self.assertNotIn("IF EXISTS", sql)

    def test_includes_qualified_table_name(self):
        manager, qe, log = _make_manager()
        sql = manager._get_drop_table_sql('"MYSCHEMA"."DBLIFT_MIGRATION_LOCK"')
        self.assertIn('"MYSCHEMA"."DBLIFT_MIGRATION_LOCK"', sql)


if __name__ == "__main__":
    unittest.main()
