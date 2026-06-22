"""OBS-04 regression: _find_undo_versions includes Python migrations with def undo().

Before this fix, _find_undo_versions() only scanned for U*.sql files, so
Python migrations with a def undo() function showed "Undoable: No" in info
even though undo would succeed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.migration.ui.data_collector import MigrationDataCollector


def _make_collector(scripts_dir: Path) -> MigrationDataCollector:
    script_manager = MagicMock()
    script_manager.extract_version.side_effect = lambda name: name.split("__")[0].lstrip("VU")

    collector = MigrationDataCollector.__new__(MigrationDataCollector)
    collector.script_manager = script_manager
    return collector


@pytest.mark.unit
class TestFindUndoVersionsPython:
    def test_sql_undo_script_detected(self, tmp_path):
        (tmp_path / "U1__undo_init.sql").write_text("DROP TABLE foo;")
        collector = _make_collector(tmp_path)
        versions = collector._find_undo_versions(tmp_path)
        assert "1" in versions

    def test_python_with_undo_fn_detected(self, tmp_path):
        script = tmp_path / "V2__create_orders.py"
        script.write_text(textwrap.dedent("""\
                def migrate(ctx):
                    ctx.execute("CREATE TABLE orders (id INT)")

                def undo(ctx):
                    ctx.execute("DROP TABLE orders")
            """))
        collector = _make_collector(tmp_path)
        versions = collector._find_undo_versions(tmp_path)
        assert "2" in versions

    def test_python_without_undo_fn_not_detected(self, tmp_path):
        script = tmp_path / "V3__create_products.py"
        script.write_text(textwrap.dedent("""\
                def migrate(ctx):
                    ctx.execute("CREATE TABLE products (id INT)")
            """))
        collector = _make_collector(tmp_path)
        versions = collector._find_undo_versions(tmp_path)
        assert "3" not in versions

    def test_both_sql_and_python_combined(self, tmp_path):
        (tmp_path / "U1__undo_init.sql").write_text("DROP TABLE foo;")
        script = tmp_path / "V2__create_orders.py"
        script.write_text("def migrate(ctx): pass\ndef undo(ctx): pass\n")
        (tmp_path / "V3__no_undo.py").write_text("def migrate(ctx): pass\n")

        collector = _make_collector(tmp_path)
        versions = collector._find_undo_versions(tmp_path)
        assert "1" in versions
        assert "2" in versions
        assert "3" not in versions

    def test_empty_dir_returns_empty_set(self, tmp_path):
        collector = _make_collector(tmp_path)
        assert collector._find_undo_versions(tmp_path) == set()

    def test_none_scripts_dir_returns_empty_set(self):
        collector = _make_collector(Path("/nonexistent"))
        assert collector._find_undo_versions(None) == set()
