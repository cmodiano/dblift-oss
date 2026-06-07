"""Regression tests for BUG-A (lexicographic sort) and BUG-B (missing commit).

BUG-A: ``undo`` without ``--target-version`` must pick the semantically
highest version, not the lexicographically highest — so V10 beats V4, not
the other way around.

BUG-B: After ``PythonMigrationExecutor.rollback_migration`` succeeds, the
undo command must commit the transaction so DML issued by ``def undo()``
is persisted. Before the fix, the changes were silently rolled back on
connection cleanup (mirrors the same-class bug on the migrate path fixed
earlier for ``_execute_via_factory``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.migration.migration import MigrationType


def _make_migration(version: str, mtype, has_undo_fn: bool = False):
    m = MagicMock()
    m.version = version
    m.type = mtype
    m.success = True
    m.script_name = f"V{version}__test"
    m.description = "test"
    m.checksum = "abc"
    if mtype == MigrationType.PYTHON:
        m.content = (
            "def migrate(ctx): pass\ndef undo(ctx): pass"
            if has_undo_fn
            else "def migrate(ctx): pass"
        )
    else:
        m.content = None
    return m


def _make_command(applied_migrations, provider=None):
    from core.migration.commands.undo_command import UndoCommand

    state_manager = MagicMock()
    migration_state = MagicMock()
    migration_state.applied_objects = applied_migrations
    state_manager.build_state.return_value = migration_state
    state_manager.get_current_version.return_value = None

    migration_rules = MagicMock()
    migration_rules.should_undo_version.return_value = (True, None)

    executor_factory = MagicMock()

    def _get_executor(migration):
        if migration.type == MigrationType.PYTHON:
            executor = MagicMock()
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
    execution_engine.provider = provider if provider is not None else MagicMock()

    history_manager = MagicMock()
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
class TestVersionSortIsSemanticNotLexicographic:
    """BUG-A: the ``versioned_migrations.sort()`` at the no-target-version path."""

    def test_v10_undone_before_v4_without_target_version(self):
        v4 = _make_migration("4", MigrationType.SQL)
        v10 = _make_migration("10", MigrationType.SQL)
        # Order in applied_objects deliberately scrambled to exercise the sort.
        cmd, _, exec_engine = _make_command([v4, v10])

        cmd.execute(scripts_dir=MagicMock())

        # The SQL undo path calls execute_migration with the undo_migration —
        # but we lack real scripts in this test, so no execute_migration call
        # will actually happen. Instead, verify the rules layer was queried
        # for V10 first (the top of the sorted list) — NOT V4.
        rules_calls = [
            call.args[0] for call in cmd.migration_rules.should_undo_version.call_args_list
        ]
        assert rules_calls, "migration_rules was never consulted"
        assert rules_calls[0] == "10", (
            f"Expected V10 to be checked first (semantic sort), got {rules_calls[0]} "
            "(lexicographic sort puts '4' > '10' by char code)"
        )

    def test_dotted_versions_sorted_semantically(self):
        v19 = _make_migration("1.9", MigrationType.SQL)
        v110 = _make_migration("1.10", MigrationType.SQL)
        cmd, _, _ = _make_command([v19, v110])

        cmd.execute(scripts_dir=MagicMock())

        rules_calls = [
            call.args[0] for call in cmd.migration_rules.should_undo_version.call_args_list
        ]
        assert rules_calls[0] == "1.10", f"1.10 should sort after 1.9, got {rules_calls[0]}"


@pytest.mark.unit
class TestPythonUndoCommitsTransaction:
    """BUG-B: Python rollback changes must be committed, not left dangling."""

    def _make_transactional_provider(self):
        from db.provider_interfaces import TransactionalProvider

        provider = MagicMock(spec=TransactionalProvider)
        return provider

    def test_commit_called_after_successful_python_rollback(self):
        provider = self._make_transactional_provider()
        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=True)

        cmd, history_manager, _ = _make_command([v1], provider=provider)
        call_order = MagicMock()
        call_order.attach_mock(history_manager.record_undo, "record_undo")
        call_order.attach_mock(provider.commit_transaction, "commit_transaction")

        result = cmd.execute(scripts_dir=MagicMock())

        assert result.undone_count == 1
        provider.begin_transaction.assert_called_once()
        history_manager.record_undo.assert_called_once()
        provider.commit_transaction.assert_called_once()
        provider.rollback_transaction.assert_not_called()
        assert [call[0] for call in call_order.mock_calls] == [
            "record_undo",
            "commit_transaction",
        ]

    def test_rollback_called_after_failed_python_rollback(self):
        provider = self._make_transactional_provider()
        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=True)
        cmd, history_manager, exec_engine = _make_command([v1], provider=provider)

        def _failing_executor(migration):
            executor = MagicMock()
            executor.supports_rollback.return_value = True
            fail = MagicMock()
            fail.success = False
            fail.error = "undo raised"
            executor.rollback_migration.return_value = fail
            return executor

        exec_engine.executor_factory.get_executor.side_effect = _failing_executor

        cmd.execute(scripts_dir=MagicMock())

        provider.begin_transaction.assert_called_once()
        provider.commit_transaction.assert_not_called()
        provider.rollback_transaction.assert_called_once()
        history_manager.record_undo.assert_not_called()

    def test_non_transactional_provider_no_commit_call(self):
        """Providers that do not implement TransactionalProvider (e.g. CosmosDB) must not get begin/commit calls."""
        provider = MagicMock()
        # spec-free MagicMock will pass isinstance() only by accident — ensure it doesn't:
        from db.provider_interfaces import TransactionalProvider

        assert not isinstance(provider, TransactionalProvider)

        v1 = _make_migration("1", MigrationType.PYTHON, has_undo_fn=True)
        cmd, _, _ = _make_command([v1], provider=provider)

        cmd.execute(scripts_dir=MagicMock())

        provider.begin_transaction.assert_not_called()
        provider.commit_transaction.assert_not_called()
