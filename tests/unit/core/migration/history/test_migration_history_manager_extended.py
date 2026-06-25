"""Extended unit tests for MigrationHistoryManager covering uncovered branches.

Target file: core/migration/history/migration_history_manager.py
Coverage focus:
- get_applied_migrations, get_applied_migration_records, get_applied_migrations_legacy
- record_migration (VERSIONED and REPEATABLE paths)
- acquire_migration_lock / release_migration_lock (success, failure, exception paths)
- validate_history_table (undo command, missing table, exception)
- create_schema_and_history_table (success, race condition retry, non-race failure)
- record_undo
- repair_checksum (success, not-updated, exception)
- get_columns_query, get_add_column_sql, get_parameter_placeholders
"""

import unittest
from unittest.mock import MagicMock, call, patch

from core.migration.history.migration_history_manager import (
    MigrationHistoryManager,
    ValidationResult,
)
from core.migration.migration import AppliedMigration, Migration, MigrationType


def _make_manager(schema="public", table="dblift_schema_history", installed_by="test_user"):
    """Build a MigrationHistoryManager with a mocked provider."""
    provider = MagicMock()
    provider.get_normalized_object_name.side_effect = lambda name: name.lower()
    provider.table_exists.return_value = True
    logger = MagicMock()

    return MigrationHistoryManager(
        provider=provider,
        schema=schema,
        installed_by=installed_by,
        logger=logger,
        table_name=table,
    )


def _make_migration(migration_type=MigrationType.SQL, name="V1__test.sql"):
    m = MagicMock(spec=Migration)
    m.script_name = name
    m.version = "1"
    m.description = "test migration"
    m.type = migration_type
    m.checksum = 12345
    return m


class TestValidationResult(unittest.TestCase):
    def test_default_success(self):
        r = ValidationResult()
        self.assertTrue(r.success)
        self.assertEqual(r.error_message, "")


class TestGetAppliedMigrations(unittest.TestCase):
    def test_returns_migration_list_from_records(self):
        mgr = _make_manager()
        applied1 = MagicMock(spec=AppliedMigration)
        applied1.to_migration.return_value = MagicMock(spec=Migration)
        applied2 = MagicMock(spec=AppliedMigration)
        applied2.to_migration.return_value = MagicMock(spec=Migration)

        with patch.object(mgr, "get_applied_migration_records", return_value=[applied1, applied2]):
            result = mgr.get_applied_migrations()

        self.assertEqual(len(result), 2)
        applied1.to_migration.assert_called_once_with(logger=mgr.logger)

    def test_returns_empty_list_when_no_records(self):
        mgr = _make_manager()
        with patch.object(mgr, "get_applied_migration_records", return_value=[]):
            result = mgr.get_applied_migrations()
        self.assertEqual(result, [])


class TestGetAppliedMigrationRecords(unittest.TestCase):
    def test_calls_provider_and_maps_to_applied_migrations(self):
        mgr = _make_manager()
        row = {
            "script": "V1__test.sql",
            "version": "1",
            "description": "test",
            "type": "VERSIONED",
            "checksum": 12345,
            "success": True,
            "execution_time": 100,
            "installed_on": None,
            "installed_by": "user",
        }
        mgr.provider.get_applied_migrations.return_value = [row]

        records = mgr.get_applied_migration_records()

        mgr.provider.get_applied_migrations.assert_called_once_with(mgr.schema, mgr.history_table)
        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], AppliedMigration)

    def test_returns_empty_list_when_provider_empty(self):
        mgr = _make_manager()
        mgr.provider.get_applied_migrations.return_value = []
        records = mgr.get_applied_migration_records()
        self.assertEqual(records, [])


class TestGetAppliedMigrationsLegacy(unittest.TestCase):
    def test_returns_migration_objects(self):
        mgr = _make_manager()
        mgr.provider.get_applied_migrations.return_value = [
            {
                "script": "V1__test.sql",
                "version": "1",
                "description": "test",
                "type": "VERSIONED",
                "checksum": 12345,
                "success": True,
                "execution_time": 100,
                "installed_on": None,
                "installed_by": "user",
            }
        ]
        result = mgr.get_applied_migrations_legacy()
        self.assertEqual(len(result), 1)


class TestRecordMigration(unittest.TestCase):
    def test_records_versioned_migration(self):
        mgr = _make_manager()
        migration = _make_migration(MigrationType.SQL)

        mgr.record_migration(migration, success=True, execution_time=200)

        mgr.provider.record_migration.assert_called_once()
        call_args = mgr.provider.record_migration.call_args
        info = call_args[0][1]
        self.assertEqual(info["script"], migration.script_name)
        self.assertTrue(info["success"])
        self.assertEqual(info["execution_time"], 200)
        self.assertEqual(info["installed_by"], mgr.installed_by)

    def test_records_repeatable_migration_with_debug_logs(self):
        mgr = _make_manager()
        migration = _make_migration(MigrationType.REPEATABLE, name="R__repeat.sql")
        migration.sql_content = "SELECT 1"

        mgr.record_migration(migration, success=True, execution_time=50)

        mgr.provider.record_migration.assert_called_once()
        debug_calls = [str(c) for c in mgr.logger.debug.call_args_list]
        self.assertTrue(any("REPEATABLE" in c for c in debug_calls))

    def test_success_false_stored_as_false(self):
        mgr = _make_manager()
        migration = _make_migration()

        mgr.record_migration(migration, success=False, execution_time=100)

        info = mgr.provider.record_migration.call_args[0][1]
        self.assertFalse(info["success"])

    def test_records_type_name_not_value(self):
        mgr = _make_manager()
        migration = _make_migration(MigrationType.SQL)

        mgr.record_migration(migration, success=True, execution_time=10)

        info = mgr.provider.record_migration.call_args[0][1]
        # MigrationType.SQL.name is "SQL"
        self.assertEqual(info["type"], "SQL")

    def test_repeatable_without_sql_content_attr(self):
        """Migration without sql_content attribute: graceful fallback."""
        mgr = _make_manager()
        migration = _make_migration(MigrationType.REPEATABLE)
        # Don't set sql_content — hasattr will be False

        mgr.record_migration(migration, success=True, execution_time=10)

        mgr.provider.record_migration.assert_called_once()


class TestAcquireMigrationLock(unittest.TestCase):
    def test_returns_true_when_acquired(self):
        mgr = _make_manager()
        mgr.provider.acquire_migration_lock.return_value = True
        self.assertTrue(mgr.acquire_migration_lock())

    def test_returns_false_when_not_acquired(self):
        mgr = _make_manager()
        mgr.provider.acquire_migration_lock.return_value = False
        self.assertFalse(mgr.acquire_migration_lock())


class TestReleaseMigrationLock(unittest.TestCase):
    def test_returns_true_on_success(self):
        mgr = _make_manager()
        mgr.provider.release_migration_lock.return_value = True
        result = mgr.release_migration_lock()
        self.assertTrue(result)

    def test_returns_false_when_result_falsy_logs_warning(self):
        mgr = _make_manager()
        mgr.provider.release_migration_lock.return_value = False
        mgr.provider.log = MagicMock()
        result = mgr.release_migration_lock()
        self.assertFalse(result)
        mgr.provider.log.warning.assert_called_once()

    def test_returns_false_on_exception(self):
        mgr = _make_manager()
        mgr.provider.release_migration_lock.side_effect = Exception("lock error")
        mgr.provider.log = MagicMock()
        result = mgr.release_migration_lock()
        self.assertFalse(result)
        mgr.provider.log.warning.assert_called_once()

    def test_returns_false_when_no_provider(self):
        mgr = _make_manager()
        mgr.provider = None
        result = mgr.release_migration_lock()
        self.assertFalse(result)

    def test_exception_without_provider_log_swallowed(self):
        mgr = _make_manager()
        mgr.provider.release_migration_lock.side_effect = Exception("lock error")
        mgr.provider.log = None  # no log
        result = mgr.release_migration_lock()
        self.assertFalse(result)


class TestValidateHistoryTable(unittest.TestCase):
    def test_undo_without_history_table_fails(self):
        mgr = _make_manager()
        mgr.provider.table_exists.return_value = False

        result = mgr.validate_history_table(command="undo")

        self.assertFalse(result.success)
        self.assertIn("Cannot undo", result.error_message)
        mgr.logger.error.assert_called_once()

    def test_migrate_without_history_table_succeeds(self):
        mgr = _make_manager()
        mgr.provider.table_exists.return_value = False

        result = mgr.validate_history_table(command="migrate")

        self.assertTrue(result.success)
        debug_calls = [str(c) for c in mgr.logger.debug.call_args_list]
        self.assertTrue(any("does not exist yet" in c for c in debug_calls))

    def test_history_table_exists_returns_success(self):
        mgr = _make_manager()
        mgr.provider.table_exists.return_value = True

        result = mgr.validate_history_table(command="migrate")

        self.assertTrue(result.success)

    def test_provider_exception_returns_error(self):
        mgr = _make_manager()
        mgr.provider.table_exists.side_effect = Exception("db connection lost")

        result = mgr.validate_history_table(command="migrate")

        self.assertFalse(result.success)
        self.assertIn("Error checking history table", result.error_message)
        mgr.logger.error.assert_called_once()

    def test_default_command_is_migrate(self):
        mgr = _make_manager()
        mgr.provider.table_exists.return_value = False

        result = mgr.validate_history_table()  # default command

        self.assertTrue(result.success)


class TestCreateSchemaAndHistoryTable(unittest.TestCase):
    def test_create_schema_false_skips_schema_creation(self):
        """create_schema=False (regular migrate) must not call create_schema_if_not_exists."""
        mgr = _make_manager()
        mgr.provider.create_history_table_if_not_exists.return_value = None

        mgr.create_schema_and_history_table(create_schema=False)

        mgr.provider.create_schema_if_not_exists.assert_not_called()
        mgr.provider.create_history_table_if_not_exists.assert_called_once()

    def test_create_schema_true_calls_schema_creation(self):
        """create_schema=True (baseline) must call create_schema_if_not_exists."""
        mgr = _make_manager()
        mgr.provider.create_schema_if_not_exists.return_value = None
        mgr.provider.create_history_table_if_not_exists.return_value = None

        mgr.create_schema_and_history_table(create_schema=True)

        mgr.provider.create_schema_if_not_exists.assert_called_once_with(mgr.schema)
        mgr.provider.create_history_table_if_not_exists.assert_called_once()

    def test_race_condition_retries(self):
        mgr = _make_manager()
        call_count = [0]

        def create_history_side_effect(schema, create_schema, table):
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("duplicate key already exists")

        mgr.provider.create_schema_if_not_exists.return_value = None
        mgr.provider.create_history_table_if_not_exists.side_effect = create_history_side_effect

        with patch("time.sleep"):  # don't actually sleep in tests
            mgr.create_schema_and_history_table(create_schema=True)

        self.assertEqual(call_count[0], 2)
        warning_calls = [str(c) for c in mgr.logger.warning.call_args_list]
        self.assertTrue(any("Concurrent" in c for c in warning_calls))

    def test_non_race_exception_reraises_immediately(self):
        mgr = _make_manager()
        mgr.provider.create_schema_if_not_exists.side_effect = Exception("permission denied")

        with self.assertRaises(Exception, msg="permission denied"):
            mgr.create_schema_and_history_table(create_schema=True)

    def test_race_condition_exhausted_reraises(self):
        mgr = _make_manager()
        mgr.provider.create_schema_if_not_exists.return_value = None
        mgr.provider.create_history_table_if_not_exists.side_effect = Exception("already exists")

        with patch("time.sleep"):
            with self.assertRaises(Exception):
                mgr.create_schema_and_history_table(create_schema=True)

    def test_rollback_on_race_retry(self):
        mgr = _make_manager()
        call_count = [0]

        def create_side_effect(schema, create_schema, table):
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("already exists")

        mgr.provider.create_schema_if_not_exists.return_value = None
        mgr.provider.create_history_table_if_not_exists.side_effect = create_side_effect

        with patch("time.sleep"):
            mgr.create_schema_and_history_table(create_schema=True)

        mgr.provider.rollback_transaction.assert_called()


class TestRecordUndo(unittest.TestCase):
    def test_delegates_to_provider(self):
        mgr = _make_manager()
        mgr.provider.record_undo.return_value = True
        migration = _make_migration()
        migration.version = "1.2.3"
        migration.script_name = "V1__test.sql"

        result = mgr.record_undo(migration)

        self.assertTrue(result)
        mgr.provider.record_undo.assert_called_once_with(
            mgr.schema, "1.2.3", mgr.history_table, "V1__test.sql"
        )

    def test_returns_false_when_not_undone(self):
        mgr = _make_manager()
        mgr.provider.record_undo.return_value = False
        migration = _make_migration()
        migration.script_name = "V1__test.sql"

        result = mgr.record_undo(migration)

        self.assertFalse(result)

    def test_handles_non_string_script_name(self):
        """Non-string script_name should be treated as None."""
        mgr = _make_manager()
        mgr.provider.record_undo.return_value = True
        migration = _make_migration()
        migration.script_name = 12345  # not a str

        mgr.record_undo(migration)

        call_args = mgr.provider.record_undo.call_args[0]
        self.assertIsNone(call_args[3])  # script_name argument should be None


class TestRepairChecksum(unittest.TestCase):
    def test_returns_true_on_success(self):
        mgr = _make_manager()
        mgr.provider.repair_migration_history.return_value = True

        result = mgr.repair_checksum("V1__test.sql", 99999)

        self.assertTrue(result)
        mgr.provider.repair_migration_history.assert_called_once_with(
            mgr.schema,
            "V1__test.sql",
            99999,
            success_value=True,
            table_name=mgr.history_table,
        )

    def test_returns_false_and_logs_warning_when_not_updated(self):
        mgr = _make_manager()
        mgr.provider.repair_migration_history.return_value = False

        result = mgr.repair_checksum("V1__test.sql", 12345)

        self.assertFalse(result)
        mgr.logger.warning.assert_called_once()

    def test_returns_false_and_logs_error_on_exception(self):
        mgr = _make_manager()
        mgr.provider.repair_migration_history.side_effect = Exception("db error")

        result = mgr.repair_checksum("V1__test.sql", 12345)

        self.assertFalse(result)
        mgr.logger.error.assert_called_once()


class TestGetColumnsQuery(unittest.TestCase):
    def test_delegates_to_provider(self):
        mgr = _make_manager()
        mgr.provider.get_columns_query.return_value = (
            "SELECT column_name FROM information_schema.columns WHERE table_name='t'"
        )

        result = mgr.get_columns_query("t")

        mgr.provider.get_columns_query.assert_called_once_with(mgr.schema, "t")
        self.assertIsNotNone(result)


class TestGetAddColumnSql(unittest.TestCase):
    def test_delegates_to_provider(self):
        mgr = _make_manager()
        mgr.provider.get_add_column_sql.return_value = "ALTER TABLE t ADD COLUMN x INT"

        result = mgr.get_add_column_sql("t", "x", "INT")

        mgr.provider.get_add_column_sql.assert_called_once_with(mgr.schema, "t", "x", "INT")
        self.assertEqual(result, "ALTER TABLE t ADD COLUMN x INT")


class TestGetParameterPlaceholders(unittest.TestCase):
    def test_delegates_to_provider(self):
        mgr = _make_manager()
        mgr.provider.get_parameter_placeholders.return_value = "?, ?, ?"

        result = mgr.get_parameter_placeholders(3)

        mgr.provider.get_parameter_placeholders.assert_called_once_with(3)
        self.assertEqual(result, "?, ?, ?")


if __name__ == "__main__":
    unittest.main()
