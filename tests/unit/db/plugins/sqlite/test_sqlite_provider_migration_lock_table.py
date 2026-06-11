"""BUG-04 regression: SQLiteProvider declares MIGRATION_LOCK_TABLE.

Before this fix, ``SQLiteProvider`` inherited from ``BaseProvider`` and never
defined ``MIGRATION_LOCK_TABLE``. Cleanup filters and internal-table guards
expect the lock-table name to be declared by the provider.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestSqliteProviderMigrationLockTable:
    def test_attribute_declared_on_class(self):
        """The attribute must be reachable on the class without instantiation."""
        from db.plugins.sqlite.provider import SQLiteProvider

        assert hasattr(SQLiteProvider, "MIGRATION_LOCK_TABLE")
        assert SQLiteProvider.MIGRATION_LOCK_TABLE == "dblift_migration_lock"

    def test_uses_standard_lock_table_name(self):
        """Cleanup relies on the standard lock table name."""
        from db.plugins.sqlite.provider import SQLiteProvider

        assert SQLiteProvider.MIGRATION_LOCK_TABLE == "dblift_migration_lock"
