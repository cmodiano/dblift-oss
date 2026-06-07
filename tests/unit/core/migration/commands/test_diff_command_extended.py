"""Extended unit tests for diff_command.py.

Covers previously untested paths to push coverage from ~24% toward 60%+:
  - DiffCommand construction (context and legacy paths)
  - execute() — connection error, no applied objects, snapshot load paths
  - _diff_using_snapshot — None payload, no service, accuracy warnings
  - _log_diff_summary and all _log_*_diffs static methods
  - _log_diff_header / _log_diff_footer
  - _log_validation_results (introspection quality + validation metadata)
  - ignore_unmanaged branch
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

from core.comparison.diff_models import SchemaDiff
from core.logger.console import render_panel_to_str
from core.logger.results import DiffResult
from core.migration.commands._diff_object_specs import _OBJECT_TYPE_SPECS
from core.migration.commands._diff_output import (
    log_diff_footer,
    log_diff_header,
    log_event_diffs,
    log_extension_diffs,
    log_foreign_data_wrapper_diffs,
    log_foreign_server_diffs,
    log_function_diffs,
    log_index_diffs,
    log_package_diffs,
    log_procedure_diffs,
    log_sequence_diffs,
    log_synonym_diffs,
    log_table_diffs,
    log_trigger_diffs,
    log_user_defined_type_diffs,
    log_view_diffs,
)
from core.migration.commands._diff_snapshot import run_snapshot_diff
from core.migration.commands.diff_command import DiffCommand
from core.migration.state.migration_state import MigrationState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cmd(
    dialect="postgresql",
    schema="public",
    snapshot_service=None,
    log=None,
    provider=None,
    state_manager=None,
    history_manager=None,
):
    """Build a DiffCommand with minimal mocked collaborators."""
    config = MagicMock()
    config.database.type = dialect
    config.database.schema = schema

    _log = log or MagicMock()
    _provider = provider or MagicMock()
    _sm = state_manager or MagicMock()
    _hm = history_manager or MagicMock()

    cmd = DiffCommand(
        config=config,
        log=_log,
        provider=_provider,
        script_manager=MagicMock(),
        history_manager=_hm,
        validator=MagicMock(),
        execution_engine=MagicMock(),
        migration_helpers=MagicMock(),
        state_manager=_sm,
        migration_ui=MagicMock(),
        migration_rules=MagicMock(),
        snapshot_service=snapshot_service,
    )
    return cmd


def _make_schema_diff(**kwargs):
    """Return a SchemaDiff with all list attrs defaulting to []."""
    diff = SchemaDiff(object_name="public", schema_name="public")
    for k, v in kwargs.items():
        setattr(diff, k, v)
    return diff


def _schema_diff_with_values():
    """Build a SchemaDiff that has at least one entry per object type list."""
    diff = SchemaDiff(object_name="public", schema_name="public")
    diff.missing_tables = ["missing_tbl"]
    diff.extra_tables = ["extra_tbl"]
    diff.missing_views = ["missing_view"]
    diff.extra_views = ["extra_view"]
    diff.missing_indexes = ["missing_idx"]
    diff.extra_indexes = ["extra_idx"]
    diff.missing_sequences = ["missing_seq"]
    diff.extra_sequences = ["extra_seq"]
    diff.missing_triggers = ["missing_trg"]
    diff.extra_triggers = ["extra_trg"]
    diff.missing_procedures = ["missing_proc"]
    diff.extra_procedures = ["extra_proc"]
    diff.missing_functions = ["missing_fn"]
    diff.extra_functions = ["extra_fn"]
    diff.missing_synonyms = ["missing_syn"]
    diff.extra_synonyms = ["extra_syn"]
    diff.missing_packages = ["missing_pkg"]
    diff.extra_packages = ["extra_pkg"]
    diff.missing_user_defined_types = ["missing_udt"]
    diff.extra_user_defined_types = ["extra_udt"]
    diff.missing_extensions = ["missing_ext"]
    diff.extra_extensions = ["extra_ext"]
    diff.missing_foreign_data_wrappers = ["missing_fdw"]
    diff.extra_foreign_data_wrappers = ["extra_fdw"]
    diff.missing_foreign_servers = ["missing_srv"]
    diff.extra_foreign_servers = ["extra_srv"]
    diff.missing_events = ["missing_evt"]
    diff.extra_events = ["extra_evt"]
    return diff


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestDiffCommandConstruction(unittest.TestCase):
    def test_snapshot_service_stored(self):
        svc = MagicMock()
        cmd = _make_cmd(snapshot_service=svc)
        self.assertIs(cmd.snapshot_service, svc)

    def test_snapshot_service_defaults_to_none(self):
        cmd = _make_cmd()
        self.assertIsNone(cmd.snapshot_service)

    def test_log_defaults_to_nulllog_when_none(self):
        from core.logger import NullLog

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        cmd = DiffCommand(
            config=config,
            log=None,
            provider=MagicMock(),
            script_manager=MagicMock(),
            history_manager=MagicMock(),
            validator=MagicMock(),
            execution_engine=MagicMock(),
            migration_helpers=MagicMock(),
            state_manager=MagicMock(),
            migration_ui=MagicMock(),
            migration_rules=MagicMock(),
        )
        self.assertIsInstance(cmd.log, NullLog)


# ---------------------------------------------------------------------------
# execute() — connection failure
# ---------------------------------------------------------------------------


class TestExecuteConnectionFailure(unittest.TestCase):
    def test_returns_error_result_when_connection_fails(self):
        provider = MagicMock()
        cmd = _make_cmd(provider=provider)

        with patch(
            "core.migration.commands.diff_command.ensure_provider_connection",
            side_effect=RuntimeError("no connection"),
        ):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertIsNotNone(result)
        self.assertIsInstance(result, DiffResult)
        self.assertFalse(result.success)
        self.assertIn("connection", result.error_message.lower())


# ---------------------------------------------------------------------------
# execute() — no applied objects
# ---------------------------------------------------------------------------


class TestExecuteNoAppliedObjects(unittest.TestCase):
    def test_returns_success_when_no_migrations_applied(self):
        state_manager = MagicMock()
        empty_state = MigrationState()
        # applied_objects is an empty list by default
        state_manager.build_state.return_value = empty_state

        cmd = _make_cmd(state_manager=state_manager, snapshot_service=MagicMock())

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertTrue(result.success)

    def test_warns_when_no_migrations_applied(self):
        log = MagicMock()
        state_manager = MagicMock()
        state_manager.build_state.return_value = MigrationState()

        cmd = _make_cmd(log=log, state_manager=state_manager, snapshot_service=MagicMock())

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            cmd.execute(scripts_dir=Path("/migrations"))

        warn_calls = [str(c) for c in log.warn.call_args_list]
        self.assertTrue(any("No migrations" in c for c in warn_calls))


# ---------------------------------------------------------------------------
# execute() — snapshot not available
# ---------------------------------------------------------------------------


class TestExecuteSnapshotNotAvailable(unittest.TestCase):
    def _make_state_with_objects(self):
        state = MigrationState()
        obj = MagicMock()
        state.applied_objects = [obj]
        return state

    def test_no_snapshot_service_returns_error(self):
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        cmd = _make_cmd(state_manager=state_manager, snapshot_service=None)

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error_message)

    def test_snapshot_service_returns_none_snapshot_returns_error(self):
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        snapshot_svc = MagicMock()
        snapshot_svc.load_latest_snapshot.return_value = None

        cmd = _make_cmd(
            state_manager=state_manager,
            snapshot_service=snapshot_svc,
        )

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertFalse(result.success)

    def test_cosmosdb_snapshot_none_shows_cosmos_hint(self):
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        snapshot_svc = MagicMock()
        snapshot_svc.load_latest_snapshot.return_value = None

        cmd = _make_cmd(
            dialect="cosmosdb",
            state_manager=state_manager,
            snapshot_service=snapshot_svc,
        )

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertFalse(result.success)
        # NoSQL-specific message should appear
        self.assertIn("NoSQL", result.error_message)

    def test_snapshot_load_raises_returns_error(self):
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        snapshot_svc = MagicMock()
        snapshot_svc.load_latest_snapshot.side_effect = RuntimeError("DB error")

        cmd = _make_cmd(
            state_manager=state_manager,
            snapshot_service=snapshot_svc,
        )

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertFalse(result.success)

    def test_snapshot_model_path_no_service_returns_error(self):
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        cmd = _make_cmd(state_manager=state_manager, snapshot_service=None)

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(
                scripts_dir=Path("/migrations"),
                snapshot_model_path=Path("/snapshots/snap.json"),
            )

        self.assertFalse(result.success)
        self.assertIn("Snapshot service", result.error_message)

    def test_snapshot_model_path_load_raises_returns_error(self):
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        snapshot_svc = MagicMock()
        snapshot_svc.load_snapshot_payload_from_path.side_effect = FileNotFoundError("not found")

        cmd = _make_cmd(
            state_manager=state_manager,
            snapshot_service=snapshot_svc,
        )

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(
                scripts_dir=Path("/migrations"),
                snapshot_model_path=Path("/snapshots/snap.json"),
            )

        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# execute() — unexpected exception
# ---------------------------------------------------------------------------


class TestExecuteUnexpectedException(unittest.TestCase):
    def test_unexpected_exception_returns_error_result(self):
        """A crash outside of any inner try/except should be caught by the outer handler."""
        state_manager = MagicMock()
        # Return a state WITH objects so we reach the snapshot loading code
        state_with_objects = MigrationState()
        state_with_objects.applied_objects = [MagicMock()]
        state_manager.build_state.return_value = state_with_objects

        snapshot_svc = MagicMock()
        # load_latest_snapshot raises an unhandled exception type not caught before outer
        snapshot_svc.load_latest_snapshot.side_effect = Exception("totally unexpected DB error")

        cmd = _make_cmd(state_manager=state_manager, snapshot_service=snapshot_svc)

        with patch("core.migration.commands.diff_command.ensure_provider_connection"):
            result = cmd.execute(scripts_dir=Path("/migrations"))

        self.assertIsInstance(result, DiffResult)
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# _diff_using_snapshot — branches
# ---------------------------------------------------------------------------


def _invoke_run_snapshot_diff(cmd, result, payload, metadata, ignore_unmanaged):
    """Bridge old-API call sites to the module-level helper.

    Mirrors the dependencies the orchestrator (DiffCommand.execute) wires when
    delegating to run_snapshot_diff, so existing assertions keep their meaning.
    """
    return run_snapshot_diff(
        result=result,
        snapshot_payload=payload,
        snapshot_metadata=metadata,
        ignore_unmanaged=ignore_unmanaged,
        snapshot_service=cmd.snapshot_service,
        provider=cmd.provider,
        config=cmd.config,
        log=cmd.log,
    )


class TestDiffUsingSnapshot(unittest.TestCase):
    def _make_full_payload(self):
        p = MagicMock()
        for spec in _OBJECT_TYPE_SPECS:
            setattr(p, spec.payload_attr, [])
        p.tables = []
        return p

    def test_returns_none_when_payload_is_none(self):
        cmd = _make_cmd(snapshot_service=MagicMock())
        result = DiffResult()
        ret = _invoke_run_snapshot_diff(cmd, result, None, {}, False)
        self.assertIsNone(ret)

    def test_returns_none_when_service_is_none(self):
        cmd = _make_cmd(snapshot_service=None)
        result = DiffResult()
        payload = self._make_full_payload()
        ret = _invoke_run_snapshot_diff(cmd, result, payload, {}, False)
        self.assertIsNone(ret)

    def test_returns_none_when_live_introspection_fails(self):
        svc = MagicMock()
        svc.build_live_payload.side_effect = RuntimeError("no live DB")
        cmd = _make_cmd(snapshot_service=svc)
        result = DiffResult()
        payload = self._make_full_payload()

        with patch("core.migration.commands._diff_snapshot.ensure_provider_connection"):
            ret = _invoke_run_snapshot_diff(cmd, result, payload, {}, False)

        self.assertIsNone(ret)

    def test_returns_none_when_connection_fails_before_live(self):
        svc = MagicMock()
        cmd = _make_cmd(snapshot_service=svc)
        result = DiffResult()
        payload = self._make_full_payload()

        with patch(
            "core.migration.commands._diff_snapshot.ensure_provider_connection",
            side_effect=RuntimeError("no conn"),
        ):
            ret = _invoke_run_snapshot_diff(cmd, result, payload, {}, False)

        self.assertIsNone(ret)

    def test_ignore_unmanaged_clears_extra_lists(self):
        svc = MagicMock()
        live_payload = self._make_full_payload()
        svc.build_live_payload.return_value = live_payload

        comparator = MagicMock()
        diff = SchemaDiff(object_name="public", schema_name="public")
        comparator.compare_schemas.return_value = diff
        for spec in _OBJECT_TYPE_SPECS:
            dm = MagicMock()
            dm.has_diffs = False
            getattr(comparator, spec.compare_method).return_value = dm

        cmd = _make_cmd(snapshot_service=svc)
        snapshot_payload = self._make_full_payload()
        result = DiffResult()

        with patch("core.migration.commands._diff_snapshot.ensure_provider_connection"):
            with patch(
                "core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator
            ):
                with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
                    with patch("core.migration.commands._diff_snapshot.AccuracyValidator") as av:
                        av.return_value.validate_all.return_value.has_issues.return_value = False
                        ret = _invoke_run_snapshot_diff(
                            cmd, result, snapshot_payload, {}, ignore_unmanaged=True
                        )

        self.assertIsNotNone(ret)
        # extra_tables cleared
        self.assertEqual(ret.schema_diff.extra_tables, [])

    def test_ignore_unmanaged_clears_linked_servers_and_modules(self):
        """Regression: extra_linked_servers and extra_modules must be cleared when ignore_unmanaged=True."""
        from core.sql_model.linked_server import LinkedServer
        from core.sql_model.module import Module

        svc = MagicMock()
        live_payload = self._make_full_payload()
        live_payload.linked_servers = [LinkedServer("remote1")]
        live_payload.modules = [Module("m1", "CREATE MODULE m1 END MODULE;")]
        svc.build_live_payload.return_value = live_payload

        comparator = MagicMock()
        diff = SchemaDiff(object_name="public", schema_name="public")
        diff.extra_linked_servers = ["remote1"]
        diff.extra_modules = ["m1"]
        comparator.compare_schemas.return_value = diff
        for spec in _OBJECT_TYPE_SPECS:
            dm = MagicMock()
            dm.has_diffs = False
            getattr(comparator, spec.compare_method).return_value = dm

        cmd = _make_cmd(snapshot_service=svc)
        snapshot_payload = self._make_full_payload()
        snapshot_payload.linked_servers = []
        snapshot_payload.modules = []
        result = DiffResult()

        with patch("core.migration.commands._diff_snapshot.ensure_provider_connection"):
            with patch(
                "core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator
            ):
                with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
                    with patch("core.migration.commands._diff_snapshot.AccuracyValidator") as av:
                        av.return_value.validate_all.return_value.has_issues.return_value = False
                        ret = _invoke_run_snapshot_diff(
                            cmd, result, snapshot_payload, {}, ignore_unmanaged=True
                        )

        self.assertIsNotNone(ret)
        self.assertEqual(ret.schema_diff.extra_linked_servers, [])
        self.assertEqual(ret.schema_diff.extra_modules, [])

    def test_accuracy_warning_logged_when_issues(self):
        log = MagicMock()
        svc = MagicMock()
        live_payload = self._make_full_payload()
        svc.build_live_payload.return_value = live_payload

        comparator = MagicMock()
        diff = SchemaDiff(object_name="public", schema_name="public")
        comparator.compare_schemas.return_value = diff
        for spec in _OBJECT_TYPE_SPECS:
            dm = MagicMock()
            dm.has_diffs = False
            getattr(comparator, spec.compare_method).return_value = dm

        cmd = _make_cmd(log=log, snapshot_service=svc)
        snapshot_payload = self._make_full_payload()
        result = DiffResult()

        accuracy_result = MagicMock()
        accuracy_result.has_issues.return_value = True
        accuracy_result.get_error_count.return_value = 1
        accuracy_result.get_warning_count.return_value = 0

        with patch("core.migration.commands._diff_snapshot.ensure_provider_connection"):
            with patch(
                "core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator
            ):
                with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
                    with patch("core.migration.commands._diff_snapshot.AccuracyValidator") as av:
                        av.return_value.validate_all.return_value = accuracy_result
                        _invoke_run_snapshot_diff(cmd, result, snapshot_payload, {}, False)

        warning_calls = [str(c) for c in log.warning.call_args_list]
        self.assertTrue(any("accuracy" in c.lower() or "Snapshot" in c for c in warning_calls))

    def test_snapshot_metadata_stored_in_result(self):
        svc = MagicMock()
        live_payload = self._make_full_payload()
        svc.build_live_payload.return_value = live_payload

        comparator = MagicMock()
        diff = SchemaDiff(object_name="public", schema_name="public")
        comparator.compare_schemas.return_value = diff
        for spec in _OBJECT_TYPE_SPECS:
            dm = MagicMock()
            dm.has_diffs = False
            getattr(comparator, spec.compare_method).return_value = dm

        cmd = _make_cmd(snapshot_service=svc)
        snapshot_payload = self._make_full_payload()
        result = DiffResult()
        metadata = {"snapshot": {"id": "abc123"}}

        with patch("core.migration.commands._diff_snapshot.ensure_provider_connection"):
            with patch(
                "core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator
            ):
                with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
                    with patch("core.migration.commands._diff_snapshot.AccuracyValidator") as av:
                        av.return_value.validate_all.return_value.has_issues.return_value = False
                        ret = _invoke_run_snapshot_diff(
                            cmd, result, snapshot_payload, metadata, False
                        )

        self.assertIsNotNone(ret)
        self.assertIn("snapshot", ret.cli_options.get("snapshot", {}))

    def test_expected_payload_stored_in_result(self):
        svc = MagicMock()
        live_payload = self._make_full_payload()
        svc.build_live_payload.return_value = live_payload

        comparator = MagicMock()
        diff = SchemaDiff(object_name="public", schema_name="public")
        comparator.compare_schemas.return_value = diff
        for spec in _OBJECT_TYPE_SPECS:
            dm = MagicMock()
            dm.has_diffs = False
            getattr(comparator, spec.compare_method).return_value = dm

        cmd = _make_cmd(snapshot_service=svc)
        snapshot_payload = self._make_full_payload()
        result = DiffResult()

        with patch("core.migration.commands._diff_snapshot.ensure_provider_connection"):
            with patch(
                "core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator
            ):
                with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
                    with patch("core.migration.commands._diff_snapshot.AccuracyValidator") as av:
                        av.return_value.validate_all.return_value.has_issues.return_value = False
                        ret = _invoke_run_snapshot_diff(cmd, result, snapshot_payload, {}, False)

        self.assertIs(ret.expected_payload, snapshot_payload)


# ---------------------------------------------------------------------------
# _log_diff_summary
# ---------------------------------------------------------------------------


class TestLogDiffSummary(unittest.TestCase):
    def test_does_nothing_when_no_schema_diff(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        result = DiffResult()
        result.schema_diff = None
        cmd._log_diff_summary(result)
        log.info.assert_not_called()

    def test_does_nothing_for_non_diff_result(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        cmd._log_diff_summary("not a diff result")
        log.info.assert_not_called()

    def test_calls_all_logger_functions(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        result = DiffResult()
        diff = _schema_diff_with_values()
        result.schema_diff = diff
        cmd._log_diff_summary(result)
        # log.info was called (details don't matter — just that it ran)
        log.info.assert_called()


# ---------------------------------------------------------------------------
# _log_diff_header / _log_diff_footer
# ---------------------------------------------------------------------------


class TestLogDiffHeaderFooter(unittest.TestCase):
    def test_header_no_diffs(self):
        log = MagicMock()
        result = DiffResult()
        result.total_differences = 0
        log_diff_header(log, result)
        plain = render_panel_to_str(log.console_print.call_args[0][0])
        self.assertIn("No differences", plain)

    def test_header_with_diffs(self):
        log = MagicMock()
        result = DiffResult()
        result.total_differences = 3
        log_diff_header(log, result)
        plain = render_panel_to_str(log.console_print.call_args[0][0])
        self.assertIn("DIFFERENCES FOUND", plain)

    def test_footer_status_success_when_no_diffs(self):
        log = MagicMock()
        result = DiffResult()
        result.total_differences = 0
        result.error_count = 0
        result.warning_count = 0
        result.info_count = 0
        log_diff_footer(log, result)
        plain = render_panel_to_str(log.console_print.call_args[0][0])
        self.assertIn("SUCCESS", plain)

    def test_footer_status_failed_when_errors(self):
        log = MagicMock()
        result = DiffResult()
        result.total_differences = 2
        result.error_count = 2
        result.warning_count = 0
        result.info_count = 0
        log_diff_footer(log, result)
        plain = render_panel_to_str(log.console_print.call_args[0][0])
        self.assertIn("FAILED", plain)

    def test_footer_status_warning_when_warnings_only(self):
        log = MagicMock()
        result = DiffResult()
        result.total_differences = 1
        result.error_count = 0
        result.warning_count = 1
        result.info_count = 0
        log_diff_footer(log, result)
        plain = render_panel_to_str(log.console_print.call_args[0][0])
        self.assertIn("WARNING", plain)


# ---------------------------------------------------------------------------
# Static _log_*_diffs methods
# ---------------------------------------------------------------------------


class TestLogTableDiffs(unittest.TestCase):
    def test_missing_tables_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_tables = ["users"]
        diff.extra_tables = []
        diff.modified_tables = []
        log_table_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("users", info_args)

    def test_extra_tables_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_tables = []
        diff.extra_tables = ["orphan"]
        diff.modified_tables = []
        log_table_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("orphan", info_args)

    def test_modified_tables_logged_with_column_details(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_tables = []
        diff.extra_tables = []
        table_diff = MagicMock()
        table_diff.table_name = "orders"
        table_diff.severity.value = "error"
        table_diff.missing_columns = ["col_a"]
        table_diff.extra_columns = []
        table_diff.modified_columns = []
        table_diff.missing_constraints = []
        table_diff.extra_constraints = []
        table_diff.modified_constraints = []
        table_diff.missing_indexes = []
        table_diff.extra_indexes = []
        # Property change flags
        table_diff.temporary_changed = False
        table_diff.filegroup_changed = False
        table_diff.memory_optimized_changed = False
        table_diff.system_versioned_changed = False
        table_diff.history_table_changed = False
        table_diff.partition_method_changed = False
        table_diff.partition_columns_changed = False
        table_diff.compress_changed = False
        table_diff.compress_type_changed = False
        table_diff.logged_changed = False
        table_diff.organize_by_changed = False
        diff.modified_tables = [table_diff]
        log_table_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("orders", info_args)
        self.assertIn("col_a", info_args)


class TestLogViewDiffs(unittest.TestCase):
    def test_missing_views_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_views = ["v_users"]
        diff.extra_views = []
        diff.modified_views = []
        log_view_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("v_users", info_args)

    def test_modified_views_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_views = []
        diff.extra_views = []
        vd = MagicMock()
        vd.view_name = "my_view"
        vd.severity.value = "warning"
        vd.definition_changed = True
        vd.materialized_changed = False
        diff.modified_views = [vd]
        log_view_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("my_view", info_args)


class TestLogIndexDiffs(unittest.TestCase):
    def test_missing_indexes_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_indexes = ["idx_email"]
        diff.extra_indexes = []
        diff.modified_indexes = []
        log_index_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("idx_email", info_args)


class TestLogSequenceDiffs(unittest.TestCase):
    def test_missing_sequences_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_sequences = ["user_id_seq"]
        diff.extra_sequences = []
        log_sequence_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("user_id_seq", info_args)


class TestLogTriggerDiffs(unittest.TestCase):
    def test_missing_triggers_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_triggers = ["trg_insert"]
        diff.extra_triggers = []
        diff.modified_triggers = []
        log_trigger_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("trg_insert", info_args)

    def test_modified_triggers_details_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_triggers = []
        diff.extra_triggers = []
        td = MagicMock()
        td.trigger_name = "my_trg"
        td.severity.value = "warning"
        td.timing_changed = ("BEFORE", "AFTER")
        td.event_changed = None
        td.definer_changed = None
        td.definition_changed = False
        td.enabled_changed = None
        diff.modified_triggers = [td]
        log_trigger_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("my_trg", info_args)
        self.assertIn("BEFORE", info_args)


class TestLogProcedureDiffs(unittest.TestCase):
    def test_missing_procedures_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_procedures = ["sp_insert"]
        diff.extra_procedures = []
        diff.modified_procedures = []
        log_procedure_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("sp_insert", info_args)

    def test_modified_procedures_parameters_changed_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_procedures = []
        diff.extra_procedures = []
        pd = MagicMock()
        pd.procedure_name = "my_proc"
        pd.severity.value = "warning"
        pd.parameters_changed = True
        pd.definition_changed = False
        diff.modified_procedures = [pd]
        log_procedure_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("parameters", info_args)


class TestLogFunctionDiffs(unittest.TestCase):
    def test_missing_functions_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_functions = ["fn_compute"]
        diff.extra_functions = []
        diff.modified_functions = []
        log_function_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("fn_compute", info_args)

    def test_modified_functions_return_type_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_functions = []
        diff.extra_functions = []
        fd = MagicMock()
        fd.function_name = "my_fn"
        fd.severity.value = "warning"
        fd.definition_changed = False
        fd.parameters_changed = False
        fd.return_type_changed = ("int", "bigint")
        diff.modified_functions = [fd]
        log_function_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("return type", info_args)


class TestLogSynonymDiffs(unittest.TestCase):
    def test_missing_synonyms_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_synonyms = ["syn_users"]
        diff.extra_synonyms = []
        diff.modified_synonyms = []
        log_synonym_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("syn_users", info_args)


class TestLogPackageDiffs(unittest.TestCase):
    def test_missing_packages_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_packages = ["pkg_core"]
        diff.extra_packages = []
        diff.modified_packages = []
        log_package_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("pkg_core", info_args)

    def test_modified_packages_spec_changed(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_packages = []
        diff.extra_packages = []
        pd = MagicMock()
        pd.package_name = "my_pkg"
        pd.severity.value = "warning"
        pd.spec_changed = True
        pd.body_changed = False
        diff.modified_packages = [pd]
        log_package_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("specification", info_args)


class TestLogUserDefinedTypeDiffs(unittest.TestCase):
    def test_missing_udts_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_user_defined_types = ["my_type"]
        diff.extra_user_defined_types = []
        diff.modified_user_defined_types = []
        log_user_defined_type_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("my_type", info_args)


class TestLogExtensionDiffs(unittest.TestCase):
    def test_missing_extensions_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_extensions = ["uuid-ossp"]
        diff.extra_extensions = []
        diff.modified_extensions = []
        log_extension_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("uuid-ossp", info_args)

    def test_modified_extensions_version_changed_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_extensions = []
        diff.extra_extensions = []
        ed = MagicMock()
        ed.extension_name = "pg_stat"
        ed.severity.value = "info"
        ed.version_changed = ("1.0", "2.0")
        ed.schema_changed = None
        diff.modified_extensions = [ed]
        log_extension_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("1.0", info_args)
        self.assertIn("2.0", info_args)


class TestLogForeignDataWrapperDiffs(unittest.TestCase):
    def test_missing_fdws_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_foreign_data_wrappers = ["my_fdw"]
        diff.extra_foreign_data_wrappers = []
        diff.modified_foreign_data_wrappers = []
        log_foreign_data_wrapper_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("my_fdw", info_args)


class TestLogForeignServerDiffs(unittest.TestCase):
    def test_missing_servers_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_foreign_servers = ["my_server"]
        diff.extra_foreign_servers = []
        diff.modified_foreign_servers = []
        log_foreign_server_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("my_server", info_args)


class TestLogEventDiffs(unittest.TestCase):
    def test_missing_events_logged(self):
        log = MagicMock()
        diff = MagicMock()
        diff.missing_events = ["evt_cleanup"]
        diff.extra_events = []
        diff.modified_events = []
        log_event_diffs(log, diff)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("evt_cleanup", info_args)


# ---------------------------------------------------------------------------
# _log_validation_results
# ---------------------------------------------------------------------------


class TestLogValidationResults(unittest.TestCase):
    def test_empty_metadata_returns_early(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        cmd._log_validation_results({})
        log.info.assert_not_called()

    def test_none_metadata_returns_early(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        cmd._log_validation_results(None)
        log.info.assert_not_called()

    def test_no_validation_or_quality_returns_early(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        cmd._log_validation_results({"snapshot": {"id": "abc"}})
        log.info.assert_not_called()

    def test_introspection_quality_logged(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        metadata = {
            "introspection_quality": {
                "completeness_score": 0.95,
                "confidence_level": "HIGH",
                "error_count": 0,
                "warning_count": 1,
            }
        }
        cmd._log_validation_results(metadata)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("Completeness", info_args)

    def test_introspection_quality_errors_logged_at_warning(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        metadata = {
            "introspection_quality": {
                "completeness_score": 0.5,
                "confidence_level": "LOW",
                "error_count": 3,
                "warning_count": 0,
            }
        }
        cmd._log_validation_results(metadata)
        warn_calls = [str(c) for c in log.warning.call_args_list]
        self.assertTrue(any("Errors" in c or "error" in c.lower() for c in warn_calls))

    def test_validation_results_passed_logged(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        metadata = {
            "validation": {
                "overall_passed": True,
                "confidence": {},
                "total_errors": 0,
                "total_warnings": 0,
            }
        }
        cmd._log_validation_results(metadata)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("PASSED", info_args)

    def test_validation_results_failed_logged(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        metadata = {
            "validation": {
                "overall_passed": False,
                "confidence": {"confidence_level": "LOW", "overall_score": 0.4},
                "total_errors": 5,
                "total_warnings": 2,
            }
        }
        cmd._log_validation_results(metadata)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        self.assertIn("FAILED", info_args)

    def test_confidence_breakdown_logged(self):
        log = MagicMock()
        cmd = _make_cmd(log=log)
        metadata = {
            "validation": {
                "overall_passed": True,
                "confidence": {
                    "confidence_level": "HIGH",
                    "overall_score": 0.9,
                    "breakdown": {
                        "error_rate": {"score": 1.0},
                        "completeness": {"score": 0.95},
                    },
                },
                "total_errors": 0,
                "total_warnings": 0,
            }
        }
        cmd._log_validation_results(metadata)
        info_args = " ".join(str(c) for c in log.info.call_args_list)
        # error_rate should be shown as Success_Rate (BUG-06)
        self.assertIn("Success_Rate", info_args)
        self.assertIn("Completeness", info_args)


# ---------------------------------------------------------------------------
# execute() — ignore_unmanaged flag integration
# ---------------------------------------------------------------------------


class TestExecuteIgnoreUnmanaged(unittest.TestCase):
    def _make_state_with_objects(self):
        state = MigrationState()
        state.applied_objects = [MagicMock()]
        return state

    def test_ignore_unmanaged_passed_to_diff_snapshot(self):
        """When ignore_unmanaged=True is passed to execute(), the flag reaches run_snapshot_diff."""
        state_manager = MagicMock()
        state_manager.build_state.return_value = self._make_state_with_objects()

        snapshot_svc = MagicMock()
        snapshot = MagicMock()
        snapshot.payload = MagicMock()
        snapshot.metadata = {}
        snapshot_svc.load_latest_snapshot.return_value = snapshot

        captured_ignore = {}

        def capturing_diff(**kwargs):
            captured_ignore["value"] = kwargs.get("ignore_unmanaged")
            dr = DiffResult()
            dr.success = True
            dr.schema_diff = SchemaDiff(object_name="public", schema_name="public")
            return dr

        cmd = _make_cmd(
            state_manager=state_manager,
            snapshot_service=snapshot_svc,
        )

        with patch(
            "core.migration.commands.diff_command.run_snapshot_diff",
            side_effect=capturing_diff,
        ):
            with patch("core.migration.commands.diff_command.ensure_provider_connection"):
                cmd.execute(scripts_dir=Path("/migrations"), ignore_unmanaged=True)

        self.assertTrue(captured_ignore.get("value"))


if __name__ == "__main__":
    unittest.main()
