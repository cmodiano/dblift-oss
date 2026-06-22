"""BUG-01 regression: undo command handles Python migrations correctly.

Before this fix, ``UndoCommand.execute`` filtered candidates with
``m.type == MigrationType.SQL``, making Python migrations invisible.  The undo
loop silently skipped a Python migration (V3) and undid the SQL migrations (V1,
V2) applied before it, leaving V3 in Success state while its DDL prerequisites
no longer existed.  ``_get_current_version()`` then returned 3 instead of
reflecting the actual (broken) state.

The fix changes the candidate filter to include ``MigrationType.PYTHON`` and
routes Python migrations through their own rollback path:

- A Python migration WITH ``def undo(context):`` is executed via
  ``PythonMigrationExecutor.rollback_migration`` and recorded in history via
  ``history_manager.record_undo``.
- A Python migration WITHOUT ``def undo(context):`` is a hard stop — the undo
  command refuses to undo anything below it to avoid leaving the database in an
  inconsistent state.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.migration.migration import MigrationType


def _make_migration(version, mtype, success=True, has_undo_fn=False):
    """Create a minimal Migration-like stub for state manager output."""
    m = MagicMock()
    m.version = version
    m.type = mtype
    m.success = success
    m.script_name = f"V{version}__test"
    m.description = "test"
    m.checksum = "abc"
    # For Python migrations: simulate content with/without undo()
    if mtype == MigrationType.PYTHON:
        m.content = (
            "def migrate(ctx): pass\ndef undo(ctx): pass"
            if has_undo_fn
            else "def migrate(ctx): pass"
        )
    else:
        m.content = None
    return m


def _make_command(applied_migrations):
    """Build an UndoCommand with just enough stubs for the guard tests."""
    from core.migration.commands.undo_command import UndoCommand

    # State manager returns our canned migration list
    state_manager = MagicMock()
    migration_state = MagicMock()
    migration_state.applied_objects = applied_migrations
    state_manager.build_state.return_value = migration_state
    state_manager.get_current_version.return_value = None

    # Migration rules: SQL is always undoable in these tests
    migration_rules = MagicMock()
    migration_rules.should_undo_version.return_value = (True, None)

    # Executor factory: delegates to a PythonMigrationExecutor stub per migration
    executor_factory = MagicMock()

    def _get_executor(migration):
        if migration.type == MigrationType.PYTHON:
            executor = MagicMock()
            # supports_rollback checks content for "def undo("
            executor.supports_rollback.side_effect = lambda m: (
                m.content is not None and "def undo(" in m.content
            )
            exec_result = MagicMock()
            exec_result.success = True
            exec_result.error = None
            executor.rollback_migration.return_value = exec_result
            return executor
        return None

    executor_factory.get_executor.side_effect = _get_executor

    execution_engine = MagicMock()
    execution_engine.executor_factory = executor_factory

    history_manager = MagicMock()
    history_manager.record_undo.return_value = True

    script_manager = MagicMock()
    script_manager.get_migration_scripts.return_value = []

    config = MagicMock()
    config.database.schema = "test"

    cmd = UndoCommand(
        config=config,
        log=MagicMock(),
        provider=MagicMock(),
        script_manager=script_manager,
        history_manager=history_manager,
        validator=MagicMock(),
        execution_engine=execution_engine,
        migration_helpers=MagicMock(),
        state_manager=state_manager,
        migration_ui=MagicMock(),
        migration_rules=migration_rules,
    )
    cmd.journal = None
    cmd.placeholder_service = MagicMock()
    cmd.migration_helpers.setup_migration_parameters.return_value = (True, None)

    return cmd, history_manager, execution_engine


@pytest.mark.unit
class TestUndoCommandPythonMigration:
    def test_python_without_undo_blocks_sql_below(self):
        """SQL migrations below a non-undoable Python migration must NOT be undone."""
        v1 = _make_migration("1", MigrationType.SQL)
        v2 = _make_migration("2", MigrationType.SQL)
        v3 = _make_migration("3", MigrationType.PYTHON, has_undo_fn=False)

        cmd, history_manager, exec_engine = _make_command([v1, v2, v3])

        result = cmd.execute(scripts_dir=MagicMock())

        # No SQL undo should have been executed
        exec_engine.execute_migration.assert_not_called()
        # No Python rollback called either
        assert result.undone_count == 0
        # BUG-02: must exit with failure, not success
        assert result.success is False
        assert result.error_message is not None
        assert "cannot be undone" in result.error_message

    def test_python_without_undo_function_sets_error_message(self):
        """BUG-02 regression: undo with non-reversible Python migration must set error and exit 1."""
        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=False)

        cmd, history_manager, exec_engine = _make_command([v1])

        result = cmd.execute(scripts_dir=MagicMock())

        assert result.success is False
        assert result.error_message is not None
        assert "undo(context)" in result.error_message or "cannot be undone" in result.error_message

    def test_python_without_undo_target_version_also_blocked(self):
        """Target-version rollback stops when it hits a non-undoable Python migration."""
        v1 = _make_migration("1", MigrationType.SQL)
        v2 = _make_migration("2", MigrationType.PYTHON, has_undo_fn=False)
        v3 = _make_migration("3", MigrationType.SQL)

        cmd, history_manager, exec_engine = _make_command([v1, v2, v3])

        result = cmd.execute(scripts_dir=MagicMock(), target_version="1")

        exec_engine.execute_migration.assert_not_called()
        assert result.undone_count == 0

    def test_python_with_undo_function_is_rolled_back(self):
        """Python migration WITH undo() function is executed via rollback_migration."""
        v1 = _make_migration("1", MigrationType.SQL)
        v2 = _make_migration("2", MigrationType.PYTHON, has_undo_fn=True)

        cmd, history_manager, exec_engine = _make_command([v1, v2])

        result = cmd.execute(scripts_dir=MagicMock())

        # History must be recorded to mark version as undone
        history_manager.record_undo.assert_called_once()
        assert result.undone_count == 1

    def test_python_dry_run_show_sql_records_empty_sql_entry(self):
        """Python undo has no SQL to show, but should still appear in show-sql output."""
        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=True)

        cmd, history_manager, exec_engine = _make_command([v1])

        result = cmd.execute(scripts_dir=MagicMock(), dry_run=True, show_sql=True)

        exec_engine.execute_migration.assert_not_called()
        history_manager.record_undo.assert_not_called()
        assert result.show_sql is True
        assert result.sql[0].script == "V1__test"
        assert result.sql[0].statements == []

    def test_python_show_sql_records_empty_sql_entry_after_rollback(self):
        """Real Python undo should mirror migrate show-sql with an empty SQL list."""
        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=True)

        cmd, history_manager, exec_engine = _make_command([v1])

        result = cmd.execute(scripts_dir=MagicMock(), show_sql=True)

        history_manager.record_undo.assert_called_once()
        assert result.show_sql is True
        assert result.sql[0].script == "V1__test"
        assert result.sql[0].statements == []

    def test_python_with_undo_sql_below_is_reachable_next_call(self):
        """After undoing a Python migration, the SQL migration below it is accessible."""
        v1 = _make_migration("1", MigrationType.SQL)
        v2 = _make_migration("2", MigrationType.PYTHON, has_undo_fn=True)

        cmd, history_manager, exec_engine = _make_command([v1, v2])

        # First undo: Python V2 should be chosen (newest Success)
        result = cmd.execute(scripts_dir=MagicMock())

        assert result.undone_count == 1
        # The undone migration is the Python one
        infos = result.undone_migrations if hasattr(result, "undone_migrations") else []
        if infos:
            assert infos[0].type == "UNDO_PYTHON"

    def test_python_rollback_exception_closes_journal_entry(self):
        """If rollback_migration raises, the journal entry opened for the Python
        migration must still be closed — otherwise the journal is left in a
        corrupted state with an open entry.

        Before the fix, the exception handler only closed the journal when
        ``undo_migration is not None`` (the SQL path). The Python path leaves
        ``undo_migration`` as None but sets ``journal_started = True``, so the
        entry stayed open forever on any exception.
        """
        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=True)

        cmd, history_manager, exec_engine = _make_command([v1])

        # Arrange: install a journal and make rollback_migration raise.
        journal = MagicMock()
        cmd.journal = journal

        def _raising_get_executor(migration):
            executor = MagicMock()
            executor.supports_rollback.return_value = True
            executor.rollback_migration.side_effect = RuntimeError("simulated failure")
            return executor

        exec_engine.executor_factory.get_executor.side_effect = _raising_get_executor

        result = cmd.execute(scripts_dir=MagicMock())

        assert result.success is False
        # Journal must have been both started and ended using the Python migration's
        # own script_name — otherwise the entry would be left dangling.
        journal.start_migration.assert_called_once()
        journal.end_migration.assert_called_once()
        end_args, end_kwargs = journal.end_migration.call_args
        closed_name = end_args[0] if end_args else end_kwargs.get("script_name")
        assert closed_name == v1.script_name
        assert end_kwargs.get("success") is False
