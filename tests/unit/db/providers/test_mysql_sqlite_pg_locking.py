"""Tests for MySQL, SQLite, and PostgreSQL locking managers."""

import unittest
from unittest.mock import MagicMock


class TestMySqlLockingManagerInit(unittest.TestCase):
    def _make(self):
        from db.plugins.mysql.mysql.locking_manager import MySqlLockingManager

        qe = MagicMock()
        log = MagicMock()
        return MySqlLockingManager(query_executor=qe, log=log), qe, log

    def test_stores_components(self):
        mgr, qe, log = self._make()
        self.assertIs(mgr.query_executor, qe)
        self.assertIs(mgr.log, log)

    def test_null_log_default(self):
        from core.logger import NullLog
        from db.plugins.mysql.mysql.locking_manager import MySqlLockingManager

        mgr = MySqlLockingManager(MagicMock())
        self.assertIsInstance(mgr.log, NullLog)


class TestMySqlLockingManagerCreateTable(unittest.TestCase):
    def _make(self):
        from db.plugins.mysql.mysql.locking_manager import MySqlLockingManager

        qe = MagicMock()
        return MySqlLockingManager(qe, MagicMock()), qe

    def test_skips_when_table_exists(self):
        mgr, qe = self._make()
        qe.table_exists.return_value = True
        conn = MagicMock()
        mgr.create_migration_lock_table_if_not_exists(conn, "mydb")
        qe.execute_statement.assert_not_called()

    def test_creates_when_not_exists(self):
        mgr, qe = self._make()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "mydb.dblift_migration_lock"
        conn = MagicMock()
        mgr.create_migration_lock_table_if_not_exists(conn, "mydb")
        qe.execute_statement.assert_called_once()

    def test_raises_on_error(self):
        mgr, qe = self._make()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "db.t"
        qe.execute_statement.side_effect = Exception("network failure")
        conn = MagicMock()
        with self.assertRaises(Exception):
            mgr.create_migration_lock_table_if_not_exists(conn, "db")


class TestMySqlLockingManagerAcquire(unittest.TestCase):
    def _make(self):
        from db.plugins.mysql.mysql.locking_manager import MySqlLockingManager

        qe = MagicMock()
        return MySqlLockingManager(qe, MagicMock()), qe

    def test_acquire_returns_bool(self):
        mgr, qe = self._make()
        qe.execute_query.return_value = [{"lock_result": 1}]
        conn = MagicMock()
        result = mgr.acquire_migration_lock(conn, "mydb")
        self.assertIsInstance(result, bool)

    def test_acquire_native_lock_success(self):
        mgr, qe = self._make()
        qe.execute_query.return_value = [{"lock_result": 1}]
        conn = MagicMock()
        result = mgr.acquire_migration_lock(conn, "mydb", wait_timeout_seconds=1)
        self.assertTrue(result)

    def test_acquire_lock_failure_falls_back(self):
        mgr, qe = self._make()
        qe.execute_query.return_value = [{"lock_result": 0}]
        conn = MagicMock()
        result = mgr.acquire_migration_lock(conn, "mydb", wait_timeout_seconds=0)
        self.assertIsInstance(result, bool)


class TestMySqlLockingManagerRelease(unittest.TestCase):
    def _make(self):
        from db.plugins.mysql.mysql.locking_manager import MySqlLockingManager

        qe = MagicMock()
        return MySqlLockingManager(qe, MagicMock()), qe

    def test_release_returns_bool(self):
        mgr, qe = self._make()
        qe.execute_query.return_value = [{"release_result": 1}]
        result = mgr.release_migration_lock(MagicMock(), "mydb")
        self.assertIsInstance(result, bool)

    def test_release_exception_returns_false(self):
        mgr, qe = self._make()
        qe.execute_query.side_effect = Exception("conn lost")
        result = mgr.release_migration_lock(MagicMock(), "mydb")
        self.assertFalse(result)


class TestSQLiteLockingManagerInit(unittest.TestCase):
    def _make(self):
        from db.plugins.sqlite.sqlite.locking_manager import SQLiteLockingManager

        qe = MagicMock()
        return SQLiteLockingManager(qe, MagicMock()), qe

    def test_stores_query_executor(self):
        mgr, qe = self._make()
        self.assertIs(mgr.query_executor, qe)

    def test_null_log_default(self):
        from core.logger import NullLog
        from db.plugins.sqlite.sqlite.locking_manager import SQLiteLockingManager

        mgr = SQLiteLockingManager(MagicMock())
        self.assertIsInstance(mgr.log, NullLog)


class TestSQLiteLockingManagerCreateTable(unittest.TestCase):
    def _make(self):
        from db.plugins.sqlite.sqlite.locking_manager import SQLiteLockingManager

        qe = MagicMock()
        return SQLiteLockingManager(qe, MagicMock()), qe

    def test_create_table_executes_statement(self):
        mgr, qe = self._make()
        conn = MagicMock()
        mgr.create_migration_lock_table_if_not_exists(conn, "main")
        qe.execute_statement.assert_called_once()

    def test_raises_on_error(self):
        mgr, qe = self._make()
        qe.execute_statement.side_effect = Exception("disk full")
        with self.assertRaises(Exception):
            mgr.create_migration_lock_table_if_not_exists(MagicMock(), "main")


class TestSQLiteLockingManagerAcquireRelease(unittest.TestCase):
    def _make(self):
        from db.plugins.sqlite.sqlite.locking_manager import SQLiteLockingManager

        qe = MagicMock()
        return SQLiteLockingManager(qe, MagicMock()), qe

    def test_acquire_returns_bool(self):
        mgr, qe = self._make()
        qe.execute_statement.return_value = None
        result = mgr.acquire_migration_lock(MagicMock(), "main")
        self.assertIsInstance(result, bool)

    def test_release_returns_bool(self):
        mgr, qe = self._make()
        qe.execute_statement.return_value = None
        result = mgr.release_migration_lock(MagicMock(), "main")
        self.assertIsInstance(result, bool)


class TestPostgreSQLAdvisoryLockKey(unittest.TestCase):
    def test_get_advisory_lock_key_deterministic(self):
        from db.plugins.postgresql.postgresql.locking_manager import _get_advisory_lock_key

        k1 = _get_advisory_lock_key("public")
        k2 = _get_advisory_lock_key("public")
        self.assertEqual(k1, k2)

    def test_different_schemas_different_keys(self):
        from db.plugins.postgresql.postgresql.locking_manager import _get_advisory_lock_key

        self.assertNotEqual(
            _get_advisory_lock_key("public"),
            _get_advisory_lock_key("private"),
        )

    def test_returns_integer(self):
        from db.plugins.postgresql.postgresql.locking_manager import _get_advisory_lock_key

        self.assertIsInstance(_get_advisory_lock_key("test"), int)


class TestPostgreSQLLockingManagerInit(unittest.TestCase):
    def _make(self):
        from db.plugins.postgresql.postgresql.locking_manager import PostgreSqlLockingManager

        qe = MagicMock()
        return PostgreSqlLockingManager(qe, MagicMock()), qe

    def test_stores_executor(self):
        mgr, qe = self._make()
        self.assertIs(mgr.query_executor, qe)

    def test_null_log_default(self):
        from core.logger import NullLog
        from db.plugins.postgresql.postgresql.locking_manager import PostgreSqlLockingManager

        mgr = PostgreSqlLockingManager(MagicMock())
        self.assertIsInstance(mgr.log, NullLog)


class TestPostgreSQLLockingManagerCreateTable(unittest.TestCase):
    def _make(self):
        from db.plugins.postgresql.postgresql.locking_manager import PostgreSqlLockingManager

        qe = MagicMock()
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        return PostgreSqlLockingManager(qe, MagicMock()), qe

    def test_creates_table_when_not_exists(self):
        mgr, qe = self._make()
        qe.table_exists.return_value = False
        mgr.create_migration_lock_table_if_not_exists(MagicMock(), "public")
        qe.execute_statement.assert_called_once()

    def test_always_runs_if_not_exists(self):
        # PG uses CREATE TABLE IF NOT EXISTS — always calls execute_statement
        mgr, qe = self._make()
        mgr.create_migration_lock_table_if_not_exists(MagicMock(), "public")
        qe.execute_statement.assert_called_once()

    def test_raises_on_error(self):
        mgr, qe = self._make()
        qe.execute_statement.side_effect = Exception("network error")
        with self.assertRaises(Exception):
            mgr.create_migration_lock_table_if_not_exists(MagicMock(), "public")


class TestPostgreSQLLockingManagerAdvisory(unittest.TestCase):
    def _make(self):
        from db.plugins.postgresql.postgresql.locking_manager import PostgreSqlLockingManager

        qe = MagicMock()
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        return PostgreSqlLockingManager(qe, MagicMock()), qe

    def test_acquire_advisory_lock_success(self):
        mgr, qe = self._make()
        qe.execute_query.return_value = [{"pg_try_advisory_lock": True}]
        result = mgr.acquire_migration_lock(MagicMock(), "public")
        self.assertIsInstance(result, bool)

    def test_acquire_returns_bool_on_exception(self):
        # PG falls back to table-based locking on advisory lock failure
        mgr, qe = self._make()
        qe.execute_query.side_effect = Exception("conn lost")
        result = mgr.acquire_migration_lock(MagicMock(), "public")
        self.assertIsInstance(result, bool)

    def test_release_advisory_lock(self):
        mgr, qe = self._make()
        qe.execute_query.return_value = [{"pg_advisory_unlock": True}]
        result = mgr.release_migration_lock(MagicMock(), "public")
        self.assertIsInstance(result, bool)

    def test_release_returns_false_on_exception(self):
        mgr, qe = self._make()
        qe.execute_query.side_effect = Exception("conn lost")
        result = mgr.release_migration_lock(MagicMock(), "public")
        self.assertFalse(result)
