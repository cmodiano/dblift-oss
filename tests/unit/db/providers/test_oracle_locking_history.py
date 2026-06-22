"""Tests for Oracle locking manager and history manager."""

import unittest
from unittest.mock import MagicMock, call, patch


class TestOracleLockingManagerStatic(unittest.TestCase):
    def _cls(self):
        from db.plugins.oracle.oracle.locking_manager import OracleLockingManager

        return OracleLockingManager

    def test_get_lock_name_basic(self):
        cls = self._cls()
        name = cls.get_lock_name("myschema")
        self.assertTrue(name.startswith("DBLIFT_MIG_LOCK_"))
        self.assertIn("MYSCHEMA", name)

    def test_get_lock_name_uppercase(self):
        cls = self._cls()
        self.assertEqual(cls.get_lock_name("foo"), cls.get_lock_name("FOO"))

    def test_get_lock_name_truncated(self):
        cls = self._cls()
        name = cls.get_lock_name("A" * 50)
        self.assertLessEqual(len(name), 30)

    def test_get_lock_name_strips_quotes(self):
        cls = self._cls()
        name = cls.get_lock_name('"myschema"')
        self.assertNotIn('"', name)

    def test_get_lock_key_same_as_name(self):
        cls = self._cls()
        self.assertEqual(cls.get_lock_key("s1"), cls.get_lock_name("s1"))


class TestOracleLockingManagerInit(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.locking_manager import OracleLockingManager

        qe = MagicMock()
        log = MagicMock()
        return OracleLockingManager(query_executor=qe, log=log), qe, log

    def test_init_stores_components(self):
        mgr, qe, log = self._make()
        self.assertIs(mgr.query_executor, qe)
        self.assertIs(mgr.log, log)

    def test_init_null_log_default(self):
        from core.logger import NullLog
        from db.plugins.oracle.oracle.locking_manager import OracleLockingManager

        mgr = OracleLockingManager(query_executor=MagicMock())
        self.assertIsInstance(mgr.log, NullLog)


class TestOracleLockingManagerCreateTable(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.locking_manager import OracleLockingManager

        qe = MagicMock()
        log = MagicMock()
        mgr = OracleLockingManager(query_executor=qe, log=log)
        return mgr, qe, log

    def test_creates_table_when_not_exists(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        mgr.create_migration_lock_table_if_not_exists(conn, "testschema")
        qe.execute_statement.assert_called_once()

    def test_skips_when_table_exists(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = True
        mgr.create_migration_lock_table_if_not_exists(conn, "testschema")
        qe.execute_statement.assert_not_called()

    def test_ignores_already_exists_error(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.execute_statement.side_effect = Exception("already exists")
        mgr.create_migration_lock_table_if_not_exists(conn, "s")  # no raise

    def test_ignores_ora_00955(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.execute_statement.side_effect = Exception("ORA-00955: name already")
        mgr.create_migration_lock_table_if_not_exists(conn, "s")

    def test_raises_other_errors(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.execute_statement.side_effect = Exception("network error")
        with self.assertRaises(Exception):
            mgr.create_migration_lock_table_if_not_exists(conn, "s")


class TestOracleLockingManagerRelease(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.locking_manager import OracleLockingManager

        qe = MagicMock()
        return OracleLockingManager(query_executor=qe, log=MagicMock()), qe

    def test_release_no_handle(self):
        mgr, qe = self._make()
        conn = MagicMock()
        # Should not raise even with no handle stored
        result = mgr.release_migration_lock(conn, "s")
        self.assertIsInstance(result, bool)

    def test_release_table_fallback_success(self):
        mgr, qe = self._make()
        conn = MagicMock()
        qe.execute_statement.return_value = None
        mgr.release_migration_lock(conn, "s")


class TestOracleHistoryManagerInit(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.history_manager import OracleHistoryManager

        qe = MagicMock()
        so = MagicMock()
        config = MagicMock()
        log = MagicMock()
        return OracleHistoryManager(qe, so, config, log), qe, so, config, log

    def test_default_table_name_uppercase(self):
        mgr, *_ = self._make()
        self.assertEqual(mgr.DEFAULT_HISTORY_TABLE, "DBLIFT_SCHEMA_HISTORY")

    def test_get_default_table_name(self):
        mgr, *_ = self._make()
        self.assertEqual(mgr._get_default_table_name(), "DBLIFT_SCHEMA_HISTORY")


class TestOracleHistoryManagerCreateTable(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.history_manager import OracleHistoryManager

        qe = MagicMock()
        so = MagicMock()
        config = MagicMock()
        log = MagicMock()
        return OracleHistoryManager(qe, so, config, log), qe, so

    def test_creates_table_when_not_exists(self):
        mgr, qe, so = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "PUBLIC.DBLIFT_SCHEMA_HISTORY"
        mgr.create_migration_history_table_if_not_exists(conn, "PUBLIC")
        qe.execute_statement.assert_called_once()

    def test_skips_when_table_exists(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = True
        mgr.create_migration_history_table_if_not_exists(conn, "PUBLIC")
        qe.execute_statement.assert_not_called()

    def test_creates_schema_when_flag_set(self):
        mgr, qe, so = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "S.T"
        mgr.create_migration_history_table_if_not_exists(conn, "S", create_schema=True)
        # Oracle calls create_schema_if_not_exists twice: once for create_schema flag + once before table creation
        self.assertGreaterEqual(so.create_schema_if_not_exists.call_count, 1)

    def test_ignores_already_exists_error(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "S.T"
        qe.execute_statement.side_effect = Exception("already exists")
        mgr.create_migration_history_table_if_not_exists(conn, "S")  # no raise

    def test_ignores_ora_00955(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "S.T"
        qe.execute_statement.side_effect = Exception("ORA-00955")
        mgr.create_migration_history_table_if_not_exists(conn, "S")

    def test_raises_other_errors(self):
        mgr, qe, _ = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.return_value = "S.T"
        qe.execute_statement.side_effect = Exception("network timeout")
        with self.assertRaises(Exception):
            mgr.create_migration_history_table_if_not_exists(conn, "S")


class TestOracleHistoryManagerCreateHistoryTable(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.history_manager import OracleHistoryManager

        qe = MagicMock()
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        so = MagicMock()
        config = MagicMock()
        return OracleHistoryManager(qe, so, config, MagicMock()), qe

    def test_returns_create_table_sql(self):
        mgr, _ = self._make()
        sql = mgr.create_history_table("PUBLIC")
        self.assertIn("CREATE TABLE", sql)
        self.assertIn("INSTALLED_RANK", sql)

    def test_uses_schema_in_sql(self):
        mgr, _ = self._make()
        sql = mgr.create_history_table("MYSCHEMA")
        self.assertIn("MYSCHEMA", sql)


class TestOracleHistoryManagerRecordMigration(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.history_manager import OracleHistoryManager

        qe = MagicMock()
        qe.table_exists.return_value = True
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        so = MagicMock()
        config = MagicMock()
        return OracleHistoryManager(qe, so, config, MagicMock()), qe

    def test_record_migration_calls_execute(self):
        mgr, qe = self._make()
        conn = MagicMock()
        info = {
            "script": "V1__test.sql",
            "version": "1",
            "description": "test",
            "type": "SQL",
            "checksum": 123,
            "installed_by": "user",
            "execution_time": 100,
            "success": True,
        }
        mgr.record_migration(conn, "PUBLIC", info)
        qe.execute_statement.assert_called_once()

    def test_record_migration_creates_table_if_missing(self):
        mgr, qe = self._make()
        conn = MagicMock()
        qe.table_exists.return_value = False
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        info = {
            "script": "V1__test.sql",
            "version": "1",
            "description": "d",
            "type": "SQL",
            "checksum": 0,
            "installed_by": "u",
            "execution_time": 0,
            "success": True,
        }
        mgr.record_migration(conn, "S", info)
        # Should try to create the table
        self.assertTrue(qe.execute_statement.called)


class TestOracleHistoryManagerGetApplied(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.history_manager import OracleHistoryManager

        qe = MagicMock()
        qe.table_exists.return_value = True
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        so = MagicMock()
        config = MagicMock()
        return OracleHistoryManager(qe, so, config, MagicMock()), qe

    def test_returns_empty_when_no_table(self):
        mgr, qe = self._make()
        qe.table_exists.return_value = False
        conn = MagicMock()
        result = mgr.get_applied_migrations(conn, "S")
        self.assertEqual(result, [])

    def test_returns_normalized_results(self):
        mgr, qe = self._make()
        conn = MagicMock()
        qe.execute_query.return_value = [
            {
                "SCRIPT": "V1__test.sql",
                "VERSION": "1",
                "SUCCESS": 1,
                "INSTALLED_RANK": 1,
                "TYPE": "SQL",
                "DESCRIPTION": "t",
                "CHECKSUM": 123,
                "INSTALLED_BY": "u",
                "INSTALLED_ON": None,
                "EXECUTION_TIME": 100,
            }
        ]
        results = mgr.get_applied_migrations(conn, "S")
        self.assertEqual(len(results), 1)


class TestOracleHistoryManagerRecordUndo(unittest.TestCase):
    def _make(self):
        from db.plugins.oracle.oracle.history_manager import OracleHistoryManager

        qe = MagicMock()
        qe.table_exists.return_value = True
        qe.get_schema_qualified_name.side_effect = lambda s, t: f"{s}.{t}"
        so = MagicMock()
        config = MagicMock()
        return OracleHistoryManager(qe, so, config, MagicMock()), qe

    def test_record_undo_returns_true_on_success(self):
        mgr, qe = self._make()
        conn = MagicMock()
        result = mgr.record_undo(conn, "S", "1.0")
        self.assertTrue(result)

    def test_record_undo_returns_false_on_error(self):
        mgr, qe = self._make()
        qe.table_exists.return_value = True
        qe.execute_statement.side_effect = Exception("DB error")
        conn = MagicMock()
        result = mgr.record_undo(conn, "S", "1.0")
        self.assertFalse(result)
