"""Unit tests for BaseUndoManager (Story X-2 — JdbcProvider decomposition).

Mock-based: BaseUndoManager only depends on a duck-typed ``provider``
interface, so we exercise it without any JVM/JDBC setup.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from db.plugins.base_undo_manager import BaseUndoManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    table_exists: bool = True,
    query_results_sequence: list | None = None,
):
    """Build a duck-typed provider matching BaseUndoManager's contract."""
    provider = MagicMock()
    provider.log = MagicMock()
    provider.table_exists.return_value = table_exists
    provider.get_schema_qualified_name = lambda schema, name: f"{schema}.{name}"
    provider.record_migration = MagicMock()

    if query_results_sequence is None:
        query_results_sequence = []
    counter = {"n": 0}

    def _exec(sql, params=None):
        idx = counter["n"]
        counter["n"] += 1
        if idx < len(query_results_sequence):
            return query_results_sequence[idx]
        return []

    provider.execute_query = MagicMock(side_effect=_exec)
    provider.executed_queries_count = counter
    return provider


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordUndo:
    def test_returns_false_when_table_not_exists(self):
        provider = _make_provider(table_exists=False)
        result = BaseUndoManager(provider).record_undo("public", "1")
        assert result is False
        provider.execute_query.assert_not_called()
        provider.log.warning.assert_called_once()

    def test_nominal_path_records_undo(self):
        # 1) check UNDO_SQL → empty 2) lookup migration → found
        provider = _make_provider(
            query_results_sequence=[
                [],
                [{"description": "init", "installed_rank": 1}],
            ]
        )
        result = BaseUndoManager(provider).record_undo("public", "1")
        assert result is True
        provider.record_migration.assert_called_once()
        args, _ = provider.record_migration.call_args
        schema, undo_info, table_name = args
        assert schema == "public"
        assert table_name == "dblift_schema_history"
        assert undo_info["type"] == "UNDO_SQL"
        assert undo_info["checksum"] == 0  # Batch-6 BUG-02 sentinel
        assert undo_info["success"] is True
        assert undo_info["script"] == "U1__init.sql"

    def test_returns_false_when_no_migration_found(self):
        provider = _make_provider(query_results_sequence=[[], []])
        result = BaseUndoManager(provider).record_undo("public", "missing")
        assert result is False
        provider.record_migration.assert_not_called()
        provider.log.warning.assert_called_once()

    def test_returns_false_when_already_undone_and_not_reapplied(self):
        # 1) existing UNDO_SQL row 2) reapplied check → empty
        provider = _make_provider(
            query_results_sequence=[
                [{"description": "undo", "installed_rank": 2, "script": "U1__init.sql"}],
                [],
            ]
        )
        result = BaseUndoManager(provider).record_undo("public", "1")
        assert result is False
        provider.record_migration.assert_not_called()

    def test_can_undo_again_after_reapplication(self):
        # 1) existing UNDO_SQL 2) reapplied found 3) latest migration row
        provider = _make_provider(
            query_results_sequence=[
                [{"description": "undo", "installed_rank": 2, "script": "U1__init.sql"}],
                [{"installed_rank": 3}],
                [{"description": "init", "installed_rank": 3}],
            ]
        )
        result = BaseUndoManager(provider).record_undo("public", "1")
        assert result is True
        provider.record_migration.assert_called_once()

    def test_custom_table_name_is_used(self):
        provider = _make_provider(query_results_sequence=[[], [{"description": "x"}]])
        BaseUndoManager(provider).record_undo("public", "1", table_name="custom_history")
        provider.table_exists.assert_called_with("public", "custom_history")
        args, _ = provider.record_migration.call_args
        assert args[2] == "custom_history"

    def test_default_table_name_when_none(self):
        provider = _make_provider(query_results_sequence=[[], [{"description": "x"}]])
        BaseUndoManager(provider).record_undo("public", "1", table_name=None)
        provider.table_exists.assert_called_with("public", "dblift_schema_history")


# ---------------------------------------------------------------------------
# BUG-01 behavioural — PYTHON type filter (in addition to source-level test)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPythonTypeFilter:
    def test_main_query_filters_by_sql_or_python(self):
        # Capture the SQL of the second query (description lookup)
        provider = _make_provider(query_results_sequence=[[], [{"description": "x"}]])
        BaseUndoManager(provider).record_undo("public", "1")
        sqls = [c.args[0] for c in provider.execute_query.call_args_list]
        # Second query is the description lookup
        assert "type IN ('SQL', 'PYTHON')" in sqls[1]
        assert "type = 'SQL'" not in sqls[1]

    def test_reapplied_query_filters_by_sql_or_python(self):
        provider = _make_provider(
            query_results_sequence=[
                [{"description": "undo", "installed_rank": 2}],
                [{"installed_rank": 3}],
                [{"description": "x"}],
            ]
        )
        BaseUndoManager(provider).record_undo("public", "1")
        sqls = [c.args[0] for c in provider.execute_query.call_args_list]
        # Second query is the reapplied detection
        assert "type IN ('SQL', 'PYTHON')" in sqls[1]
