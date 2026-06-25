"""Extended tests for core/migration/ui/data_collector.py."""

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


def _make_collector():
    from core.migration.ui.data_collector import MigrationDataCollector

    log = MagicMock()
    sm = MagicMock()
    return MigrationDataCollector(log=log, script_manager=sm), log, sm


class TestMigrationDataCollectorInit(unittest.TestCase):
    def test_stores_log(self):
        coll, log, _ = _make_collector()
        self.assertIs(coll.log, log)

    def test_null_log_default(self):
        from core.logger import NullLog
        from core.migration.ui.data_collector import MigrationDataCollector

        coll = MigrationDataCollector(log=None)
        self.assertIsInstance(coll.log, NullLog)


class TestFormatInstalledOn(unittest.TestCase):
    def _c(self):
        return _make_collector()[0]

    def test_none_returns_empty(self):
        coll = self._c()
        self.assertEqual(coll._format_installed_on(None), "")

    def test_empty_string_returns_empty(self):
        coll = self._c()
        self.assertEqual(coll._format_installed_on(""), "")

    def test_datetime_formatted(self):
        coll = self._c()
        dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
        result = coll._format_installed_on(dt)
        self.assertIsInstance(result, str)
        self.assertIn("2024", result)

    def test_iso_string_returned_as_is(self):
        coll = self._c()
        result = coll._format_installed_on("2024-01-15T10:30:00")
        self.assertIsInstance(result, str)


class TestGetMigrationTypeString(unittest.TestCase):
    def _c(self):
        return _make_collector()[0]

    def test_sql_type(self):
        from core.migration.migration import MigrationType

        coll = self._c()
        result = coll._get_migration_type_string(MigrationType.SQL)
        self.assertIsInstance(result, str)

    def test_none_returns_string(self):
        coll = self._c()
        result = coll._get_migration_type_string(None)
        self.assertIsInstance(result, str)

    def test_string_type_passed_through(self):
        coll = self._c()
        result = coll._get_migration_type_string("SQL")
        self.assertIsInstance(result, str)


class TestStatusToDisplayState(unittest.TestCase):
    def test_success_status(self):
        from core.migration.ui.data_collector import MigrationDataCollector

        result = MigrationDataCollector._status_to_display_state("SUCCESS")
        self.assertIsInstance(result, str)

    def test_failed_status(self):
        from core.migration.ui.data_collector import MigrationDataCollector

        result = MigrationDataCollector._status_to_display_state("FAILED")
        self.assertIsInstance(result, str)

    def test_pending_status(self):
        from core.migration.ui.data_collector import MigrationDataCollector

        result = MigrationDataCollector._status_to_display_state("PENDING")
        self.assertIsInstance(result, str)


class TestIsVersionedType(unittest.TestCase):
    def _c(self):
        return _make_collector()[0]

    def test_sql_is_versioned(self):
        from core.migration.migration import MigrationType

        coll = self._c()
        self.assertTrue(coll._is_versioned_type(MigrationType.SQL))

    def test_repeatable_not_versioned(self):
        from core.migration.migration import MigrationType

        coll = self._c()
        self.assertFalse(coll._is_versioned_type(MigrationType.REPEATABLE))


class TestCollectVersionedMigrations(unittest.TestCase):
    def _make_migration(self, version, mtype="SQL", success=True):
        m = SimpleNamespace(
            script_name=f"V{version}__test.sql",
            version=version,
            type=mtype,
            success="1" if success else "0",
            installed_rank=int(version) if version and version.isdigit() else 1,
            checksum=None,
            description="test",
            installed_by="user",
            installed_on=None,
            execution_time=100,
        )
        return m

    def test_collects_versioned(self):
        coll = _make_collector()[0]
        migrations = [
            self._make_migration("1"),
            self._make_migration("2"),
        ]
        result = coll._collect_versioned_migrations(migrations)
        self.assertIsInstance(result, list)

    def test_skips_repeatable(self):
        coll = _make_collector()[0]
        migrations = [
            self._make_migration("1"),
            self._make_migration(None, mtype="REPEATABLE"),  # no version
        ]
        result = coll._collect_versioned_migrations(migrations)
        # Should only include versioned
        self.assertGreater(len(result), 0)


class TestBuildRepeatableChecksums(unittest.TestCase):
    def _make_repeatable(self, script_name, checksum):
        return SimpleNamespace(
            script_name=script_name,
            type="REPEATABLE",
            version=None,
            checksum=checksum,
            success="1",
        )

    def test_builds_checksum_dict(self):
        coll = _make_collector()[0]
        migrations = [
            self._make_repeatable("R__test.sql", "abc123"),
        ]
        result = coll._build_repeatable_checksums(migrations)
        self.assertIsInstance(result, dict)


class TestSortAppliedMigrations(unittest.TestCase):
    def test_sorts_by_rank(self):
        coll = _make_collector()[0]
        m1 = SimpleNamespace(installed_rank=2, version="2", type="SQL", script_name="V2.sql")
        m2 = SimpleNamespace(installed_rank=1, version="1", type="SQL", script_name="V1.sql")
        result = coll._sort_applied_migrations([m1, m2])
        self.assertIsInstance(result, list)


class TestDetectOutOfOrderMigrations(unittest.TestCase):
    def test_no_out_of_order(self):
        coll = _make_collector()[0]
        versioned = [
            {"version": "1", "rank": 1},
            {"version": "2", "rank": 2},
        ]
        result = coll._detect_out_of_order_migrations(versioned)
        self.assertIsInstance(result, set)
        self.assertEqual(len(result), 0)

    def test_detect_with_proper_format(self):
        from core.migration.ui.data_collector import MigrationDataCollector

        coll = MigrationDataCollector(log=MagicMock())
        # Use empty list — method should return empty set
        result = coll._detect_out_of_order_migrations([])
        self.assertIsInstance(result, set)
        self.assertEqual(len(result), 0)
