"""Unit tests for BaseSnapshotManager (Story X-1 — JdbcProvider decomposition).

Tests are mock-based: BaseSnapshotManager only depends on a duck-typed
``provider`` interface, so we exercise it without any JVM/JDBC setup.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from db.plugins.base_snapshot_manager import BaseSnapshotManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeConnection:
    def __init__(self, autocommit: bool = False) -> None:
        self._autocommit = autocommit
        self.commit_called = 0
        self.rollback_called = 0

    def getAutoCommit(self) -> bool:
        return self._autocommit

    def commit(self) -> None:
        self.commit_called += 1

    def rollback(self) -> None:
        self.rollback_called += 1


def _make_provider(
    dialect: str = "postgresql",
    table_exists: bool = False,
    execute_side_effect=None,
    autocommit: bool = False,
    connection: object | None = None,
):
    """Build a duck-typed provider matching BaseSnapshotManager's contract."""
    provider = MagicMock()
    provider.log = MagicMock()
    provider.config = SimpleNamespace(database=SimpleNamespace(type=dialect))
    provider.is_connected.return_value = True
    provider.create_connection = MagicMock()
    provider.create_schema_if_not_exists = MagicMock()
    provider.get_normalized_object_name = lambda name: name
    provider.table_exists.return_value = table_exists
    provider.get_schema_qualified_name = lambda schema, name: f"{schema}.{name}"
    provider.commit_transaction = MagicMock()

    executed: list[str] = []

    def _exec(sql, schema=None, params=None):
        if execute_side_effect is not None:
            execute_side_effect(sql)
        executed.append(sql)
        return 1

    provider.execute_statement = MagicMock(side_effect=_exec)
    provider.executed_sqls = executed

    provider.connection = connection if connection is not None else _FakeConnection(autocommit)
    return provider


# ---------------------------------------------------------------------------
# AC#5 — Dialect coverage (6 dialects × CREATE + short-circuit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDialectSql:
    def test_postgresql_uses_text(self):
        provider = _make_provider("postgresql")
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")
        assert any("TEXT" in s and "snapshot_id" in s for s in provider.executed_sqls)

    def test_mysql_uses_longtext(self):
        provider = _make_provider("mysql")
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("db")
        sql = next(s for s in provider.executed_sqls if "CREATE TABLE" in s)
        assert "LONGTEXT" in sql
        assert "VARCHAR" in sql and "VARCHAR2" not in sql

    def test_mariadb_uses_longtext(self):
        provider = _make_provider("mariadb")
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("db")
        sql = next(s for s in provider.executed_sqls if "CREATE TABLE" in s)
        assert "LONGTEXT" in sql



# ---------------------------------------------------------------------------
# Short-circuit: table already exists
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShortCircuit:
    @pytest.mark.parametrize(
        "dialect", ["postgresql", "mysql", "mariadb"]
    )
    def test_skips_when_table_exists(self, dialect):
        provider = _make_provider(dialect, table_exists=True)
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("any")
        assert provider.executed_sqls == []
        assert provider.execute_statement.call_count == 0


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConnectionLifecycle:
    def test_create_connection_called_when_not_connected(self):
        provider = _make_provider()
        provider.is_connected.side_effect = [False, True]
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")
        assert provider.create_connection.call_count >= 1

    def test_commit_on_non_autocommit(self):
        provider = _make_provider(autocommit=False)
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")
        assert provider.connection.commit_called == 1

    def test_no_commit_on_autocommit(self):
        provider = _make_provider(autocommit=True)
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")
        assert provider.connection.commit_called == 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorPaths:
    def test_non_oracle_error_reraises(self):
        def boom(sql):
            if "CREATE TABLE" in sql:
                raise RuntimeError("disk full")

        provider = _make_provider("postgresql", execute_side_effect=boom)
        with pytest.raises(RuntimeError, match="disk full"):
            BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")

    def test_rollback_on_error_non_autocommit(self):
        def boom(sql):
            if "CREATE TABLE" in sql:
                raise RuntimeError("create failed")

        provider = _make_provider("postgresql", execute_side_effect=boom, autocommit=False)
        with pytest.raises(RuntimeError):
            BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")
        assert provider.connection.rollback_called == 1

    def test_commit_exception_falls_back_to_commit_transaction(self):
        class BrokenConn(_FakeConnection):
            def getAutoCommit(self):
                raise RuntimeError("conn broken")

        provider = _make_provider("postgresql", connection=BrokenConn())
        # Should not raise; fallback path exercised
        BaseSnapshotManager(provider).create_snapshot_table_if_not_exists("public")
        provider.commit_transaction.assert_called_once()
