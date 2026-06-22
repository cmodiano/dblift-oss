"""SQLite does not own schema snapshot persistence."""

import pytest

from config import DbliftConfig
from core.logger import NullLog
from db.plugins.sqlite.provider import SQLiteProvider


@pytest.mark.unit
def test_sqlite_provider_declares_snapshots_unsupported(tmp_path):
    config = DbliftConfig.from_dict(
        {
            "database": {"type": "sqlite", "path": str(tmp_path / "app.db")},
            "migrations": {
                "directory": str(tmp_path),
                "table": "dblift_schema_history",
            },
        }
    )
    provider = SQLiteProvider(config, NullLog())

    assert provider.supports_snapshots() is False


@pytest.mark.unit
def test_sqlite_provider_does_not_create_snapshot_table(tmp_path):
    config = DbliftConfig.from_dict(
        {
            "database": {"type": "sqlite", "path": str(tmp_path / "app.db")},
            "migrations": {
                "directory": str(tmp_path),
                "table": "dblift_schema_history",
            },
        }
    )
    provider = SQLiteProvider(config, NullLog())

    try:
        provider.create_connection()

        with pytest.raises(NotImplementedError):
            provider.create_snapshot_table_if_not_exists("main", "dblift_schema_snapshots")

        rows = provider.query_executor.execute_query(
            provider._get_connection(),
            "SELECT name FROM sqlite_master WHERE name = 'dblift_schema_snapshots'",
        )
        assert rows == []
    finally:
        provider.close()
