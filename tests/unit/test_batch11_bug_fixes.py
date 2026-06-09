"""Regression tests for the Batch 11 bug fixes (B11-BUG-01..06).

Grouped by bug number so an intentional behavioral change to any one fix is
easy to locate. Mirrors ``test_batch10_bug_fixes.py``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestBug01MySqlAtUserVariableTokenization(unittest.TestCase):
    """``BaseTokenizer._next_token`` falls through to the unknown-character
    branch on ``@`` and silently drops it. The remainder (``stmt_count``)
    was emitted as a bare identifier, so ``SET @stmt_count = 0`` became
    ``SET stmt_count = 0`` and ``SELECT @@global.read_only`` lost the
    leading ``@@``. Fix: ``MySQLTokenizer._next_token`` intercepts ``@`` and
    emits a single IDENTIFIER token covering ``@``/``@@`` plus the trailing
    identifier characters (including ``.`` for ``@@scope.var``).
    """

    def _idents(self, sql: str) -> list[str]:
        from core.sql_parser.tokens import TokenType
        from db.plugins.mysql.parser.mysql_tokenizer import MySQLTokenizer

        return [t.text for t in MySQLTokenizer(sql).tokenize() if t.type == TokenType.IDENTIFIER]

    def test_single_at_user_var_emits_one_identifier(self) -> None:
        idents = self._idents("SET @stmt_count = 0;")
        self.assertIn("@stmt_count", idents)
        self.assertNotIn("stmt_count", idents)

    def test_double_at_global_var_emits_one_identifier(self) -> None:
        idents = self._idents("SELECT @@global.read_only;")
        self.assertIn("@@global.read_only", idents)

    def test_user_var_in_expression(self) -> None:
        idents = self._idents("SELECT @x + 1, @y FROM t;")
        self.assertIn("@x", idents)
        self.assertIn("@y", idents)

    def test_user_var_in_string_is_not_a_variable(self) -> None:
        from core.sql_parser.tokens import TokenType
        from db.plugins.mysql.parser.mysql_tokenizer import MySQLTokenizer

        for t in MySQLTokenizer("SELECT '@not_a_var';").tokenize():
            if t.type == TokenType.IDENTIFIER:
                self.assertNotIn("@not_a_var", t.text)

    def test_statement_split_preserves_user_var(self) -> None:
        from db.plugins.mysql.parser.mysql_statement_parser import MySQLStatementParser
        from db.plugins.mysql.parser.mysql_tokenizer import MySQLTokenizer

        sql = "SET @stmt_count = 0;\nINSERT INTO logs (n) VALUES (@stmt_count);\n"
        tokens = MySQLTokenizer(sql).tokenize()
        stmts = MySQLStatementParser(tokens).split_statements()
        self.assertTrue(any("@stmt_count" in s for s in stmts))


class TestBug06SqliteRecordUndo(unittest.TestCase):
    """``SQLiteProvider`` previously declared ``record_migration`` but no
    ``record_undo``. ``MigrationHistoryManager.record_undo`` calls
    ``provider.record_undo(...)`` and crashed with ``AttributeError`` on
    SQLite while Oracle/SQL Server shipped the same delegation. The default
    ``BaseHistoryManager.record_undo`` already creates a synthetic
    ``UNDO_SQL`` row through ``record_migration`` — the provider just needed
    to expose it. Fix: thin delegating method on ``SQLiteProvider``.
    """

    def _make_provider(self):
        from db.plugins.sqlite.provider import SQLiteProvider

        config = MagicMock()
        config.database.path = ":memory:"
        config.database.database = None
        config.database.url = None

        provider = SQLiteProvider.__new__(SQLiteProvider)
        provider.config = config
        provider.log = MagicMock()
        provider.connection = MagicMock()
        provider.connection_manager = MagicMock()
        provider.history_manager = MagicMock()
        provider.history_manager.record_undo.return_value = True
        return provider

    def test_record_undo_method_exists_on_class(self) -> None:
        from db.plugins.sqlite.provider import SQLiteProvider

        self.assertTrue(hasattr(SQLiteProvider, "record_undo"))

    def test_record_undo_delegates_to_history_manager(self) -> None:
        provider = self._make_provider()
        result = provider.record_undo("main", "1.0.0", "dblift_schema_history")
        self.assertTrue(result)
        provider.history_manager.record_undo.assert_called_once_with(
            provider.connection, "main", "1.0.0", "dblift_schema_history", None
        )

    def test_record_undo_default_table_name_is_none(self) -> None:
        provider = self._make_provider()
        provider.record_undo("main", "2.0.0")
        provider.history_manager.record_undo.assert_called_once_with(
            provider.connection, "main", "2.0.0", None, None
        )

    def test_record_undo_propagates_failure(self) -> None:
        provider = self._make_provider()
        provider.history_manager.record_undo.return_value = False
        self.assertFalse(provider.record_undo("main", "3.0.0"))

    def test_migration_history_manager_can_invoke_record_undo(self) -> None:
        from core.migration.history.migration_history_manager import MigrationHistoryManager

        provider = self._make_provider()
        history = MigrationHistoryManager.__new__(MigrationHistoryManager)
        history.provider = provider
        history.schema = "main"
        history.history_table = "dblift_schema_history"
        history.log = MagicMock()

        migration = MagicMock()
        migration.version = "9.9.9"
        migration.script_name = "V9_9_9__python_migration.py"
        history.record_undo(migration)

        provider.history_manager.record_undo.assert_called_once_with(
            provider.connection,
            "main",
            "9.9.9",
            "dblift_schema_history",
            "V9_9_9__python_migration.py",
        )

    def test_base_history_manager_records_python_script_name_for_undo(self) -> None:
        from core.migration.formats import MigrationFormat
        from core.migration.migration import AppliedMigration
        from db.plugins.base_history_manager import BaseHistoryManager

        class CapturingHistoryManager(BaseHistoryManager):
            def __init__(self):
                super().__init__(MagicMock(), MagicMock(), MagicMock(), MagicMock())
                self.recorded = None

            def create_migration_history_table_if_not_exists(
                self, connection, schema, create_schema=False, table_name="dblift_schema_history"
            ):
                pass

            def record_migration(self, connection, schema, migration_info, table_name=None):
                self.recorded = migration_info

            def get_applied_migrations(self, connection, schema, table_name=None):
                return []

            def create_history_table(self, schema, table_name):
                return ""

        history = CapturingHistoryManager()
        self.assertTrue(
            history.record_undo(
                MagicMock(), "main", "4", "dblift_schema_history", "V4__python_migration.py"
            )
        )

        self.assertIsNotNone(history.recorded)
        self.assertEqual(history.recorded["type"], "UNDO_SQL")
        self.assertEqual(history.recorded["script"], "V4__python_migration.py")

        applied = AppliedMigration.from_history_row(history.recorded)
        with patch("core.migration.formats.format_detector.logger.warning") as warning:
            migration = applied.to_migration()
        self.assertEqual(migration.format, MigrationFormat.PYTHON)
        warning.assert_not_called()

    def test_jdbc_undo_manager_records_python_script_name_for_undo(self) -> None:
        from db.plugins.base_undo_manager import BaseUndoManager

        provider = MagicMock()
        provider.table_exists.return_value = True
        provider.get_schema_qualified_name.return_value = "public.dblift_schema_history"
        provider.execute_query.side_effect = [
            [],
            [{"description": "pyfeed", "installed_rank": 7}],
        ]

        manager = BaseUndoManager(provider)

        self.assertTrue(
            manager.record_undo(
                "public",
                "7",
                "dblift_schema_history",
                "V7__pyfeed.py",
            )
        )

        undo_info = provider.record_migration.call_args.args[1]
        self.assertEqual(undo_info["script"], "V7__pyfeed.py")


if __name__ == "__main__":
    unittest.main()
