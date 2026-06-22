"""PostgreSQL history-table bootstrap locking tests."""

from unittest.mock import MagicMock

import pytest

from db.plugins.postgresql.postgresql.history_manager import PostgreSqlHistoryManager
from db.plugins.postgresql.postgresql.locking_manager import _get_advisory_lock_key

pytestmark = [pytest.mark.unit]


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def table_exists(self, connection, schema, table):
        self.calls.append(("table_exists", schema, table))
        return False

    def get_schema_qualified_name(self, schema, table):
        return f"{schema}.{table}"

    def execute_query(self, connection, sql):
        self.calls.append(("execute_query", sql))
        return []

    def execute_statement(self, connection, sql, params=None):
        self.calls.append(("execute_statement", sql, params))


def test_history_table_bootstrap_holds_advisory_lock_around_create():
    executor = RecordingExecutor()
    manager = PostgreSqlHistoryManager(executor, MagicMock(), MagicMock(), MagicMock())
    lock_key = _get_advisory_lock_key("public")

    manager.create_migration_history_table_if_not_exists(object(), "public")

    call_names = [call[0] for call in executor.calls]
    lock_index = executor.calls.index(("execute_query", f"SELECT pg_advisory_lock({lock_key})"))
    create_index = next(
        index
        for index, call in enumerate(executor.calls)
        if call[0] == "execute_statement" and "CREATE TABLE public.dblift_schema_history" in call[1]
    )
    unlock_index = executor.calls.index(("execute_query", f"SELECT pg_advisory_unlock({lock_key})"))

    assert call_names.count("execute_query") == 2
    assert lock_index < create_index < unlock_index
