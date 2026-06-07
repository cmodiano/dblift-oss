"""BUG-01 regression: record_undo must accept PYTHON migrations, not just SQL.

Python migrations are stored with ``type = 'PYTHON'`` in dblift_schema_history.
The lookup query previously hardcoded ``WHERE type = 'SQL'`` in three places,
so undoing a Python migration silently returned False without writing an
UNDO_SQL row. ``info`` then kept showing the Python migration as successful.

The fix broadens the filter to ``type IN ('SQL', 'PYTHON')`` in:
- ``BaseUndoManager.record_undo`` main query (db/plugins/base_undo_manager.py)
- ``BaseUndoManager.record_undo`` reapplied_query (db/plugins/base_undo_manager.py)
- ``SqlServerHistoryManager.record_undo`` (db/plugins/sqlserver/sqlserver/history_manager.py)

The JdbcProvider record_undo was extracted into ``BaseUndoManager`` in
Story X-2; the source-level assertions now target the new module.
"""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
class TestJdbcProviderRecordUndoPython:
    def test_record_undo_query_accepts_python_type(self):
        """Source-level assertion: the record_undo query must include PYTHON."""
        from db.plugins.base_undo_manager import BaseUndoManager

        body = inspect.getsource(BaseUndoManager.record_undo)
        # Main description-lookup query must not be type='SQL'-only.
        assert "type = 'SQL'" not in body, "record_undo still uses type='SQL' exclusively"
        assert "type IN ('SQL', 'PYTHON')" in body, "record_undo missing PYTHON in type filter"

    def test_reapplied_query_accepts_python_type(self):
        """The reapplied-detection query must also include PYTHON."""
        from db.plugins.base_undo_manager import BaseUndoManager

        body = inspect.getsource(BaseUndoManager.record_undo)
        # Both SELECTs should reference PYTHON (one main, one reapplied).
        assert body.count("type IN ('SQL', 'PYTHON')") >= 2


@pytest.mark.unit
class TestSqlServerRecordUndoPython:
    def test_sqlserver_record_undo_query_accepts_python_type(self):
        from pathlib import Path

        src = Path("db/plugins/sqlserver/sqlserver/history_manager.py").read_text(encoding="utf-8")
        assert "type = 'SQL'" not in src, "sqlserver record_undo still uses type='SQL' exclusively"
        assert "type IN ('SQL', 'PYTHON')" in src
