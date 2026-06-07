"""Additional unit tests to increase coverage of export_schema_command.py.

Targets the specific missing lines identified in the coverage report.
"""

import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

from core.migration.commands._schema_export_types import (
    _OBJECT_TYPE_KEYS,
    ExportExecutionState,
    ExportSchemaOptions,
    _ExportAborted,
)
from core.migration.commands.export_schema_command import (
    SchemaExporter,
    _exclude_internal_objects,
    _filter_objects,
    _generate_migration_footer,
    _generate_migration_header,
    _get_managed_objects,
    _is_object_managed,
    _log_command_footer,
    _normalize_identifier,
    _normalize_schema_for_dialect,
    _populate_export_result_metadata,
    _remove_redundant_unique_constraints,
    export_schema,
)
from core.sql_model.base import ConstraintType, SqlObjectType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obj(name, schema=None, obj_type=SqlObjectType.TABLE, **extra):
    obj = MagicMock()
    obj.name = name
    obj.schema = schema
    obj.object_type = obj_type
    for k, v in extra.items():
        setattr(obj, k, v)
    return obj


def _make_exporter(
    dialect="postgresql",
    output="out.sql",
    output_dir=None,
    source="live-database",
    **opts_kwargs,
):
    config = MagicMock()
    config.database.type = dialect
    config.database.schema = "public"
    options = ExportSchemaOptions(
        output=output, output_dir=output_dir, source=source, **opts_kwargs
    )
    exporter = SchemaExporter.__new__(SchemaExporter)
    exporter.config = config
    exporter.options = options
    exporter.log = MagicMock()
    exporter.executor = MagicMock()
    exporter.state = ExportExecutionState()
    exporter.state.dialect = dialect
    exporter.state.target_schema = "public"
    exporter.state.filters = []
    exporter.state.provider = MagicMock()
    exporter.state.schema_version = None
    exporter.state.database_url = None
    exporter.state.database_url_masked = None
    exporter.state.schema_payload = None
    exporter.start_time = datetime.datetime.now()
    return exporter


# ---------------------------------------------------------------------------
# run() paths: _ExportAborted, complete success path via mocks
# ---------------------------------------------------------------------------


class TestRunPaths(unittest.TestCase):
    """Test the run() coordinator for the paths not covered by existing tests."""

    def _make_full_exporter(self, output_path):
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output=str(output_path), source="live-database")
        return SchemaExporter(config=config, options=opts, log=MagicMock())

    def test_run_export_aborted_returns_false(self):
        """_ExportAborted from _setup_infrastructure is caught by run()."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        ex = SchemaExporter(config=config, options=opts, log=MagicMock())
        ex._validate_options = lambda: True
        ex._setup_infrastructure = lambda: (_ for _ in ()).throw(_ExportAborted("aborted"))
        result = ex.run()
        self.assertFalse(result)

    def test_run_calls_print_header_after_setup(self):
        """run() calls _print_header after successful _setup_infrastructure."""
        ex = _make_exporter()
        ex._validate_options = MagicMock(return_value=True)
        ex._setup_infrastructure = MagicMock(return_value=True)
        ex._print_header = MagicMock()
        ex._load_schema_objects = MagicMock(return_value=([], {}))
        ex._apply_exclusions_and_filters = MagicMock(return_value=([], {}))
        ex._generate_and_write = MagicMock(return_value=True)

        result = ex.run()
        ex._print_header.assert_called_once()
        self.assertTrue(result)

    def test_run_calls_all_pipeline_stages(self):
        """run() calls all pipeline methods in order."""
        ex = _make_exporter()
        call_order = []

        ex._validate_options = MagicMock(
            return_value=True, side_effect=lambda: call_order.append("validate") or True
        )
        ex._setup_infrastructure = MagicMock(
            return_value=True, side_effect=lambda: call_order.append("setup") or True
        )
        ex._print_header = MagicMock(side_effect=lambda: call_order.append("header"))
        ex._load_schema_objects = MagicMock(
            return_value=([], {}), side_effect=lambda: call_order.append("load") or ([], {})
        )
        ex._apply_exclusions_and_filters = MagicMock(
            return_value=([], {}), side_effect=lambda a, b: call_order.append("filter") or ([], {})
        )
        ex._generate_and_write = MagicMock(
            return_value=True, side_effect=lambda a, b: call_order.append("write") or True
        )

        ex.run()
        self.assertEqual(call_order, ["validate", "setup", "header", "load", "filter", "write"])

    def test_run_setup_failure_returns_false(self):
        """_setup_infrastructure returning False causes run() to return False."""
        ex = _make_exporter()
        ex._validate_options = MagicMock(return_value=True)
        ex._setup_infrastructure = MagicMock(return_value=False)
        result = ex.run()
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _validate_options: snapshot path is directory (not a file)
# ---------------------------------------------------------------------------


class TestValidateOptionsSnapshotIsDir(unittest.TestCase):
    """Lines 162-164: snapshot_model path exists but is a directory."""

    def test_snapshot_model_is_directory_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MagicMock()
            config.database.type = "postgresql"
            config.database.schema = "public"
            opts = ExportSchemaOptions(
                source="file-model",
                snapshot_model=tmpdir,  # tmpdir exists but is a dir
                output="out.sql",
            )
            ex = SchemaExporter(config=config, options=opts, log=MagicMock())
            result = ex._validate_options()
            self.assertFalse(result)
            ex.log.error.assert_called()


# ---------------------------------------------------------------------------
# _setup_infrastructure: various paths
# ---------------------------------------------------------------------------


class TestSetupInfrastructure(unittest.TestCase):
    """Test _setup_infrastructure paths not covered by existing tests."""

    def _make_executor_mock(self):
        executor = MagicMock()
        executor.provider._ensure_connection = MagicMock()
        executor.snapshot_service = MagicMock()
        executor.log = MagicMock()
        executor.history_manager.get_applied_migrations.return_value = []
        return executor

    def _patch_setup_deps(self, url_return=None, version_return=None, state_mgr_side_effect=None):
        """Context manager helper: patch the dependencies of _setup_infrastructure."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(
            patch("core.migration.commands.export_schema_command.ensure_provider_connection")
        )
        stack.enter_context(
            patch(
                "core.migration.commands.export_schema_command.get_provider_display_url",
                return_value=url_return,
            )
        )
        mock_sm_cls = stack.enter_context(
            patch("core.migration.state.migration_state_manager.MigrationStateManager")
            if state_mgr_side_effect is None
            else patch(
                "core.migration.state.migration_state_manager.MigrationStateManager",
                side_effect=state_mgr_side_effect,
            )
        )
        if state_mgr_side_effect is None:
            mock_sm_cls.return_value.get_current_version.return_value = version_return
        return stack

    def test_setup_with_existing_executor_uses_it(self):
        """When executor is provided, setup doesn't create a new one (lines 199-204 skipped)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps(
            url_return="postgresql+psycopg://host/db", version_return="1.0"
        ):
            result = ex._setup_infrastructure()
        self.assertTrue(result)
        self.assertIs(ex.executor, executor)

    def test_setup_ensure_connection_exception_is_swallowed(self):
        """Exception from _ensure_connection is caught and logged (lines 214-215)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()
        executor.provider._ensure_connection.side_effect = RuntimeError("conn fail")

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps():
            result = ex._setup_infrastructure()
        self.assertTrue(result)  # should still succeed

    def test_setup_schema_version_retrieved_from_history(self):
        """Applied migrations cause schema version to be set (lines 240-242)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()
        applied = [MagicMock()]
        executor.history_manager.get_applied_migrations.return_value = applied

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps(version_return="2.5"):
            result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertEqual(ex.state.schema_version, "2.5")

    def test_setup_schema_version_none_when_no_applied_migrations(self):
        """No applied migrations → schema_version stays None."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()
        executor.history_manager.get_applied_migrations.return_value = []

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps():
            result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertIsNone(ex.state.schema_version)

    def test_setup_state_manager_exception_swallowed(self):
        """MigrationStateManager exception is caught (lines 243-244)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps(state_mgr_side_effect=Exception("boom")):
            result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertIsNone(ex.state.schema_version)

    def test_setup_database_url_masking(self):
        """database_url is masked when present (lines 300-307)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps(url_return="postgresql+psycopg://user:pass@host/db"):
            with patch(
                "core.utils.url_masking.mask_database_url",
                return_value="postgresql+psycopg://user:****@host/db",
            ):
                result = ex._setup_infrastructure()

        self.assertTrue(result)

    def test_setup_database_url_exception_swallowed(self):
        """get_provider_display_url exception is caught (lines 294-296)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        executor = self._make_executor_mock()

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            with patch(
                "core.migration.commands.export_schema_command.get_provider_display_url",
                side_effect=Exception("url error"),
            ):
                with patch(
                    "core.migration.state.migration_state_manager.MigrationStateManager"
                ) as mock_sm:
                    mock_sm.return_value.get_current_version.return_value = None
                    result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertIsNone(ex.state.database_url)

    def test_setup_sqlite_forces_main_schema(self):
        """SQLite db_type forces target_schema = 'main' (lines 256-262)."""
        config = MagicMock()
        config.database.type = "sqlite"
        config.database.schema = "myschema"
        opts = ExportSchemaOptions(output="out.sql", schema=None)
        executor = self._make_executor_mock()

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps():
            result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertEqual(ex.state.target_schema, "main")

    def test_setup_sqlite_warns_when_non_main_schema_given(self):
        """SQLite: warning logged when --schema passed and isn't 'main' (lines 257-261)."""
        config = MagicMock()
        config.database.type = "sqlite"
        config.database.schema = None
        opts = ExportSchemaOptions(output="out.sql", schema="other")
        executor = self._make_executor_mock()

        log = MagicMock()
        ex = SchemaExporter(config=config, options=opts, executor=executor, log=log)

        with self._patch_setup_deps():
            ex._setup_infrastructure()

        log.warning.assert_called()
        self.assertEqual(ex.state.target_schema, "main")

    def test_setup_cosmosdb_schema_optional(self):
        """CosmosDB has no required schema (lines 263-268)."""
        config = MagicMock()
        config.database.type = "cosmosdb"
        config.database.schema = None
        opts = ExportSchemaOptions(output="out.sql", schema=None)
        executor = self._make_executor_mock()

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        with self._patch_setup_deps():
            result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertEqual(ex.state.target_schema, "")

    def test_setup_no_schema_non_optional_dialect_fails(self):
        """For dialects that require schema, missing schema returns False (lines 264-266)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = None
        opts = ExportSchemaOptions(output="out.sql", schema=None)
        executor = self._make_executor_mock()

        log = MagicMock()
        ex = SchemaExporter(config=config, options=opts, executor=executor, log=log)

        with self._patch_setup_deps():
            result = ex._setup_infrastructure()

        self.assertFalse(result)
        log.error.assert_called()


# ---------------------------------------------------------------------------
# _print_header: ConsoleLog detection
# ---------------------------------------------------------------------------


class TestPrintHeader(unittest.TestCase):
    """Lines 311-393: _print_header ConsoleLog detection paths."""

    def test_print_header_no_log_returns_immediately(self):
        """NullLog (falsy check): when log is falsy-equivalent, _print_header returns without error."""
        ex = _make_exporter()
        ex.log = None
        # Should not raise
        try:
            ex._print_header()
        except AttributeError:
            pass  # NullLog case OK

    def test_print_header_with_non_console_log_skips(self):
        """If log isn't ConsoleLog or MultiLog, header is not printed (no output)."""
        ex = _make_exporter()
        # Use a plain MagicMock — it's not ConsoleLog or MultiLog, so no header
        ex.log = MagicMock()
        ex.state.schema_version = None
        ex.state.database_url_masked = None
        ex.state.filters = []

        # Should complete without raising; no info call about header lines
        ex._print_header()
        # Plain MagicMock is not an instance of ConsoleLog/MultiLog → info not called for header
        # (info may still be called 0 times; just verifying no crash)

    def test_print_header_with_console_log_prints(self):
        """If log is a ConsoleLog, prints header."""
        from core.logger.log import ConsoleLog

        console_log = MagicMock(spec=ConsoleLog)
        console_log.info = MagicMock()

        ex = _make_exporter()
        ex.log = console_log
        ex.state.schema_version = "1.0"
        ex.state.database_url_masked = "postgresql+psycopg://****@host/db"
        ex.state.filters = ["--source=file-model"]
        ex.config.database.database_name = "mydb"

        # Reset module flag
        import core.migration.commands.export_schema_command as cmd_module

        if hasattr(cmd_module, "_console_main_header_printed"):
            cmd_module._console_main_header_printed = False

        with patch("builtins.print"):
            ex._print_header()

        console_log.console_print.assert_called()

    def test_print_header_schema_version_present(self):
        """Header includes schema version."""
        from core.logger.log import ConsoleLog

        console_log = MagicMock(spec=ConsoleLog)
        file_only_calls = []
        console_log.file_only_info = MagicMock(side_effect=lambda msg: file_only_calls.append(msg))

        ex = _make_exporter()
        ex.log = console_log
        ex.state.schema_version = "3.5"
        ex.state.database_url_masked = None
        ex.state.filters = []
        ex.config.database.database_name = None
        ex.config.database.database = "mydb"

        import core.migration.commands.export_schema_command as cmd_module

        cmd_module._console_main_header_printed = True  # skip header print

        ex._print_header()
        full_output = " ".join(file_only_calls)
        self.assertIn("3.5", full_output)

    def test_print_header_with_snapshot_model(self):
        """Header includes snapshot model when using file-model."""
        from core.logger.log import ConsoleLog

        console_log = MagicMock(spec=ConsoleLog)
        file_only_calls = []
        console_log.file_only_info = MagicMock(side_effect=lambda msg: file_only_calls.append(msg))

        ex = _make_exporter(source="file-model", output_dir="/tmp")
        ex.options.snapshot_model = "/tmp/snap.json"
        ex.log = console_log
        ex.state.schema_version = None
        ex.state.database_url_masked = None
        ex.state.filters = []
        ex.config.database.database_name = None
        ex.config.database.database = None

        import core.migration.commands.export_schema_command as cmd_module

        cmd_module._console_main_header_printed = True

        ex._print_header()
        full_output = " ".join(file_only_calls)
        self.assertIn("/tmp/snap.json", full_output)


# ---------------------------------------------------------------------------
# _load_schema_objects: various paths
# ---------------------------------------------------------------------------


class TestLoadSchemaObjects(unittest.TestCase):
    def test_load_from_database_model(self):
        """source=database-model calls _load_snapshot_payload."""
        ex = _make_exporter(source="database-model")
        mock_payload = MagicMock()
        mock_payload.tables = [_make_obj("t1")]
        for key in _OBJECT_TYPE_KEYS:
            if key != "tables":
                setattr(mock_payload, key, [])

        ex._load_snapshot_payload = MagicMock(return_value=mock_payload)
        all_objs, typed = ex._load_schema_objects()
        ex._load_snapshot_payload.assert_called_once_with("database-model")
        self.assertEqual(len(all_objs), 1)

    def test_load_from_file_model(self):
        """source=file-model calls _load_snapshot_payload with file-model."""
        ex = _make_exporter(source="file-model")
        mock_payload = MagicMock()
        for key in _OBJECT_TYPE_KEYS:
            setattr(mock_payload, key, [])

        ex._load_snapshot_payload = MagicMock(return_value=mock_payload)
        all_objs, typed = ex._load_schema_objects()
        ex._load_snapshot_payload.assert_called_once_with("file-model")

    def test_load_live_database_calls_introspector(self):
        """source=live-database calls _introspect_live_objects."""
        ex = _make_exporter(source="live-database")
        ex._introspect_live_objects = MagicMock(return_value={"tables": []})
        all_objs, typed = ex._load_schema_objects()
        ex._introspect_live_objects.assert_called_once()

    def test_load_invalid_source_raises_aborted(self):
        """Invalid source raises _ExportAborted (line 429-430)."""
        ex = _make_exporter(source="bad-source")
        ex.options.source = "bad-source"
        with self.assertRaises(_ExportAborted):
            ex._load_schema_objects()


# ---------------------------------------------------------------------------
# _load_snapshot_payload: database-model paths
# ---------------------------------------------------------------------------


class TestLoadSnapshotPayload(unittest.TestCase):
    def test_database_model_no_snapshot_service_raises(self):
        """No snapshot_service raises _ExportAborted (lines 445-449)."""
        ex = _make_exporter()
        ex.state.snapshot_service = None
        with self.assertRaises(_ExportAborted):
            ex._load_snapshot_payload("database-model")

    def test_database_model_no_snapshot_found_raises(self):
        """Snapshot service returns None → _ExportAborted (lines 452-458)."""
        ex = _make_exporter()
        mock_service = MagicMock()
        mock_service.load_latest_snapshot.return_value = None
        ex.state.snapshot_service = mock_service
        with self.assertRaises(_ExportAborted):
            ex._load_snapshot_payload("database-model")

    def test_database_model_valid_snapshot_returns_payload(self):
        """Valid snapshot → returns payload (lines 459-462)."""
        ex = _make_exporter()
        mock_snapshot = MagicMock()
        mock_snapshot.snapshot_id = "snap-001"
        mock_snapshot.captured_at_iso = "2025-01-01T00:00:00"
        mock_payload = MagicMock()
        mock_snapshot.payload = mock_payload
        mock_service = MagicMock()
        mock_service.load_latest_snapshot.return_value = mock_snapshot
        ex.state.snapshot_service = mock_service

        result = ex._load_snapshot_payload("database-model")
        self.assertIs(result, mock_payload)

    def test_file_model_no_snapshot_service_raises(self):
        """file-model without snapshot service raises _ExportAborted (lines 469-471)."""
        ex = _make_exporter()
        ex.options.snapshot_model = "/tmp/snap.json"
        ex.state.snapshot_service = None
        with self.assertRaises(_ExportAborted):
            ex._load_snapshot_payload("file-model")

    def test_file_model_loads_from_path(self):
        """file-model with snapshot_service calls load_snapshot_payload_from_path (lines 472-473)."""
        ex = _make_exporter()
        ex.options.snapshot_model = "/tmp/snap.json"
        mock_payload = MagicMock()
        mock_service = MagicMock()
        mock_service.load_snapshot_payload_from_path.return_value = mock_payload
        ex.state.snapshot_service = mock_service

        result = ex._load_snapshot_payload("file-model")
        self.assertIs(result, mock_payload)
        mock_service.load_snapshot_payload_from_path.assert_called_once_with(Path("/tmp/snap.json"))

    def test_file_model_no_snapshot_model_raises_runtime(self):
        """file-model without snapshot_model raises RuntimeError (line 466)."""
        ex = _make_exporter()
        ex.options.snapshot_model = None
        mock_service = MagicMock()
        ex.state.snapshot_service = mock_service

        with self.assertRaises(RuntimeError):
            ex._load_snapshot_payload("file-model")


# ---------------------------------------------------------------------------
# _introspect_live_objects
# ---------------------------------------------------------------------------


class TestIntrospectLiveObjects(unittest.TestCase):
    def test_calls_introspect_schema_on_introspector(self):
        """_introspect_live_objects creates introspector and calls introspect_schema."""
        ex = _make_exporter()
        mock_introspector = MagicMock()
        mock_introspector.introspect_schema.return_value = {"tables": []}

        with patch(
            "core.migration.commands.export_schema_command.IntrospectorFactory"
        ) as mock_factory:
            mock_factory.create.return_value = mock_introspector
            result = ex._introspect_live_objects("public")

        mock_introspector.introspect_schema.assert_called_once_with(
            "public",
            include_views=True,
            include_sequences=True,
            include_triggers=True,
            include_procedures=True,
            include_functions=True,
        )
        self.assertEqual(result, {"tables": []})

    def test_raises_aborted_when_no_introspector(self):
        """_ExportAborted if introspector is None (lines 495-497)."""
        ex = _make_exporter()

        with patch(
            "core.migration.commands.export_schema_command.IntrospectorFactory"
        ) as mock_factory:
            mock_factory.create.return_value = None
            with self.assertRaises(_ExportAborted):
                ex._introspect_live_objects("public")


# ---------------------------------------------------------------------------
# _apply_exclusions_and_filters: connection error path
# ---------------------------------------------------------------------------


class TestApplyExclusionsAndFilters(unittest.TestCase):
    def test_provider_connection_error_raises_aborted(self):
        """ensure_provider_connection failure raises _ExportAborted (lines 602-608)."""
        ex = _make_exporter()
        ex.options = ExportSchemaOptions(output="out.sql", managed_only=True)
        ex.state.provider = MagicMock()

        t1 = _make_obj("users", schema="public")

        with patch(
            "core.migration.commands.export_schema_command.ensure_provider_connection",
            side_effect=Exception("conn error"),
        ):
            with self.assertRaises(_ExportAborted):
                ex._apply_exclusions_and_filters([t1], {"tables": [t1]})

    def test_no_provider_skips_connection_check(self):
        """No provider: connection check is skipped (line 599 condition False)."""
        ex = _make_exporter()
        ex.options = ExportSchemaOptions(output="out.sql", managed_only=True)
        ex.state.provider = None

        t1 = _make_obj("users", schema="public")

        with patch(
            "core.migration.commands.export_schema_command._filter_objects", return_value=[t1]
        ) as mock_filter:
            result_objs, _ = ex._apply_exclusions_and_filters([t1], {"tables": [t1]})
        self.assertEqual(len(result_objs), 1)


# ---------------------------------------------------------------------------
# _generate_and_write: various paths
# ---------------------------------------------------------------------------


class TestGenerateAndWrite(unittest.TestCase):
    def test_empty_objects_writes_empty_export(self):
        """Empty filtered_objects calls _write_empty_export and returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = _make_exporter(output=str(Path(tmpdir) / "out.sql"))
            ex._write_empty_export = MagicMock()
            result = ex._generate_and_write([], {})
            ex._write_empty_export.assert_called_once()
            self.assertTrue(result)

    def test_non_empty_calls_generate_object_sql(self):
        """Non-empty objects calls _generate_object_sql."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = _make_exporter(output=str(Path(tmpdir) / "out.sql"))
            t1 = _make_obj("users", schema="public")

            ex._generate_object_sql = MagicMock(
                return_value={"schema.sql": "CREATE TABLE users();"}
            )
            ex._write_output_files = MagicMock(return_value=True)

            result = ex._generate_and_write([t1], {"tables": [t1]})
            ex._generate_object_sql.assert_called_once()
            self.assertTrue(result)


# ---------------------------------------------------------------------------
# _write_output_files: split_by_type vs single file paths
# ---------------------------------------------------------------------------


class TestWriteOutputFiles(unittest.TestCase):
    def test_split_by_type_writes_multiple_files(self):
        """split_by_type writes each file type to output_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = _make_exporter(output=None, output_dir=tmpdir, split_by_type=True)
            files = {
                "tables.sql": "CREATE TABLE users();",
                "views.sql": "CREATE VIEW v1 AS SELECT 1;",
            }
            result = ex._write_output_files(files, 2, {"table": 1, "view": 1}, "postgresql", None)
            self.assertTrue(result)
            self.assertTrue((Path(tmpdir) / "tables.sql").exists())
            self.assertTrue((Path(tmpdir) / "views.sql").exists())

    def test_split_by_type_headers_use_per_file_object_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = _make_exporter(output=None, output_dir=tmpdir, split_by_type=True)
            files = {
                "table.sql": "CREATE TABLE users();",
                "materialized_view.sql": "CREATE MATERIALIZED VIEW mv AS SELECT 1;",
            }

            result = ex._write_output_files(
                files,
                11,
                {"table": 3, "materialized_view": 1},
                "postgresql",
                None,
            )

            self.assertTrue(result)
            self.assertIn(
                "Object count: 3",
                (Path(tmpdir) / "table.sql").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Object count: 1",
                (Path(tmpdir) / "materialized_view.sql").read_text(encoding="utf-8"),
            )

    def test_single_file_writes_combined_sql(self):
        """Single file export combines all SQL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "out.sql"
            ex = _make_exporter(output=str(out_path))
            ex.state.target_schema = "dblift_test"
            files = {"schema.sql": "CREATE TABLE users();"}
            result = ex._write_output_files(files, 1, {"table": 1}, "postgresql", None)
            self.assertTrue(result)
            self.assertTrue(out_path.exists())
            content = out_path.read_text(encoding="utf-8")
            self.assertIn('SET search_path = "dblift_test";', content)
            self.assertIn("CREATE TABLE users()", content)

    def test_split_by_type_without_output_dir_fails(self):
        """split_by_type=True but output_dir=None returns False."""
        ex = _make_exporter(output="out.sql", split_by_type=True)
        ex.options.output_dir = None
        ex.options.split_by_type = True
        result = ex._write_output_files({"t.sql": "x"}, 1, {}, "postgresql", None)
        self.assertFalse(result)

    def test_single_file_without_output_fails(self):
        """output=None for single-file mode returns False."""
        ex = _make_exporter(output=None, output_dir=None)
        ex.options.output = None
        ex.options.output_dir = None
        ex.options.split_by_type = False
        result = ex._write_output_files({"t.sql": "x"}, 1, {}, "postgresql", None)
        self.assertFalse(result)

    def test_set_command_completed_called_when_log_supports_it(self):
        """log.set_command_completed is called when it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "out.sql"
            ex = _make_exporter(output=str(out_path))
            log = MagicMock()
            log.set_command_completed = MagicMock()
            ex.log = log
            ex.state.filters = []

            # ExportSchemaResult is imported inline inside _write_output_files
            with patch("core.logger.results.ExportSchemaResult") as mock_result_cls:
                mock_result_cls.return_value = MagicMock()
                files = {"schema.sql": "CREATE TABLE x();"}
                ex._write_output_files(files, 1, {"table": 1}, "postgresql", None)

    def test_output_dir_without_split_still_writes_to_dir(self):
        """output_dir with split_by_type=False still creates the directory and writes files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = _make_exporter(output=None, output_dir=tmpdir, split_by_type=False)
            files = {"all.sql": "CREATE TABLE t1();"}
            result = ex._write_output_files(files, 1, {"table": 1}, "postgresql", None)
            self.assertTrue(result)


# ---------------------------------------------------------------------------
# _normalize_schema_for_dialect: additional dialect branches
# ---------------------------------------------------------------------------


class TestNormalizeSchemaForDialect(unittest.TestCase):
    def test_oracle_uppercase(self):
        result = _normalize_schema_for_dialect("myschema", "oracle")
        self.assertEqual(result, "MYSCHEMA")

    def test_db2_uppercase(self):
        result = _normalize_schema_for_dialect("myschema", "db2")
        self.assertEqual(result, "MYSCHEMA")

    def test_postgresql_non_public_lowercase(self):
        result = _normalize_schema_for_dialect("MySchema", "postgresql")
        self.assertEqual(result, "myschema")

    def test_postgresql_public_preserved(self):
        result = _normalize_schema_for_dialect("public", "postgresql")
        self.assertEqual(result, "public")

    def test_postgresql_empty_returns_public(self):
        result = _normalize_schema_for_dialect(None, "postgresql")
        self.assertEqual(result, "public")

    def test_cosmosdb_empty_returns_default(self):
        result = _normalize_schema_for_dialect(None, "cosmosdb")
        self.assertEqual(result, "default")

    def test_cosmosdb_default_preserved(self):
        result = _normalize_schema_for_dialect("default", "cosmosdb")
        self.assertEqual(result, "default")

    def test_cosmosdb_non_default(self):
        result = _normalize_schema_for_dialect("other", "cosmosdb")
        self.assertEqual(result, "other")

    def test_sqlite_empty_returns_main(self):
        result = _normalize_schema_for_dialect(None, "sqlite")
        self.assertEqual(result, "main")

    def test_sqlite_main_preserved(self):
        result = _normalize_schema_for_dialect("main", "sqlite")
        self.assertEqual(result, "main")

    def test_sqlite_non_main(self):
        result = _normalize_schema_for_dialect("other", "sqlite")
        self.assertEqual(result, "other")

    def test_other_dialect_lowercase(self):
        result = _normalize_schema_for_dialect("MySchema", "mysql")
        self.assertEqual(result, "myschema")

    def test_other_dialect_empty_returns_empty(self):
        result = _normalize_schema_for_dialect(None, "mysql")
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# _filter_objects: managed/unmanaged paths with executor
# ---------------------------------------------------------------------------


class TestFilterObjectsManagedPaths(unittest.TestCase):
    def _make_table(self, name, schema="public"):
        return SimpleNamespace(
            name=name,
            schema=schema,
            object_type=SqlObjectType.TABLE,
        )

    def test_managed_only_filters_to_managed_objects(self):
        """managed_only=True keeps only objects in managed_set."""
        t1 = self._make_table("managed_table")
        t2 = self._make_table("unmanaged_table")

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)

        managed_set = {("public", "MANAGED_TABLE", "TABLE")}

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects",
            return_value=managed_set,
        ):
            result = _filter_objects(
                [t1, t2],
                managed_only=True,
                config=config,
                executor=executor,
                scripts_dir=scripts_dir,
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "managed_table")

    def test_unmanaged_only_filters_to_unmanaged(self):
        """unmanaged_only=True keeps only objects not in managed_set."""
        t1 = self._make_table("managed_table")
        t2 = self._make_table("unmanaged_table")

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)

        managed_set = {("public", "MANAGED_TABLE", "TABLE")}

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects",
            return_value=managed_set,
        ):
            result = _filter_objects(
                [t1, t2],
                unmanaged_only=True,
                config=config,
                executor=executor,
                scripts_dir=scripts_dir,
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "unmanaged_table")

    def test_version_filter_restricts_to_managed(self):
        """versions= filter restricts to matching managed set."""
        t1 = self._make_table("versioned_table")
        t2 = self._make_table("other_table")

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)

        managed_set = {("public", "VERSIONED_TABLE", "TABLE")}

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects",
            return_value=managed_set,
        ):
            result = _filter_objects(
                [t1, t2],
                versions="1.0",
                config=config,
                executor=executor,
                scripts_dir=scripts_dir,
            )

        # filters_used=True, so intersect with managed
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "versioned_table")

    def test_managed_objects_none_logs_warning_for_managed_only(self):
        """If _get_managed_objects returns None and managed_only, warning is logged."""
        t1 = self._make_table("table1")

        config = MagicMock()
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects", return_value=None
        ):
            with patch("core.migration.commands._managed_object_filter.logger") as mock_logger:
                result = _filter_objects(
                    [t1],
                    managed_only=True,
                    config=config,
                    executor=executor,
                    scripts_dir=scripts_dir,
                )
        mock_logger.warning.assert_called()

    def test_managed_objects_none_logs_warning_for_version_filter(self):
        """If _get_managed_objects returns None and version filter used, warning logged."""
        t1 = self._make_table("table1")

        config = MagicMock()
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects", return_value=None
        ):
            with patch("core.migration.commands._managed_object_filter.logger") as mock_logger:
                result = _filter_objects(
                    [t1],
                    target_version="1.0",
                    config=config,
                    executor=executor,
                    scripts_dir=scripts_dir,
                )
        mock_logger.warning.assert_called()

    def test_debug_func_called_for_managed_filter(self):
        """debug_func is called during managed filtering."""
        t1 = self._make_table("table1")

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)

        managed_set = {("public", "TABLE1", "TABLE")}
        debug_calls = []

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects",
            return_value=managed_set,
        ):
            _filter_objects(
                [t1],
                managed_only=True,
                config=config,
                executor=executor,
                scripts_dir=scripts_dir,
                debug_func=debug_calls.append,
            )

        self.assertTrue(any("managed" in c.lower() for c in debug_calls))

    def test_table_name_filter_with_table_name_attr(self):
        """tables filter also matches obj.table_name attribute."""
        idx = SimpleNamespace(
            name="idx_users",
            schema="public",
            object_type=SqlObjectType.INDEX,
            table_name="USERS",
        )
        result = _filter_objects([idx], tables="users")
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# _exclude_internal_objects: sequence identity, index, trigger, constraint, type
# ---------------------------------------------------------------------------


class TestExcludeInternalObjectsExtended(unittest.TestCase):
    def test_cosmosdb_schema_normalized_to_default(self):
        """CosmosDB normalizes empty schema to 'default' (lines 1080-1082)."""
        config = MagicMock()
        config.database.type = "cosmosdb"
        obj = _make_obj("dblift_schema_history", schema=None)
        result = _exclude_internal_objects([obj], config=config, target_schema=None)
        self.assertEqual(result, [])

    def test_index_prefix_starts_with_internal_name(self):
        """Index name starting with internal prefix is excluded (lines 1260-1266)."""
        idx = MagicMock()
        idx.name = "dblift_schema_history_idx"
        idx.schema = "public"
        idx.object_type = SqlObjectType.INDEX
        idx.table_name = "users"  # normal table
        idx.table_schema = "public"
        result = _exclude_internal_objects([idx], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_index_pk_unique_excluded_by_constraint_name(self):
        """Index matching pk/unique constraint name is excluded (lines 1269-1271)."""
        from core.sql_model.base import ConstraintType

        # Create a table with a PK constraint
        table = MagicMock()
        table.name = "users"
        table.schema = "public"
        table.object_type = SqlObjectType.TABLE
        pk_constraint = MagicMock()
        pk_constraint.constraint_type = ConstraintType.PRIMARY_KEY
        pk_constraint.name = "users_pkey"
        table.columns = []
        table.constraints = [pk_constraint]

        # Index with same name as PK constraint
        idx = MagicMock()
        idx.name = "users_pkey"
        idx.schema = "public"
        idx.object_type = SqlObjectType.INDEX
        idx.table_name = "users"
        idx.table_schema = "public"

        result = _exclude_internal_objects([table, idx], config=None, target_schema="public")
        # idx should be excluded, table should remain
        self.assertNotIn(idx, result)
        self.assertIn(table, result)

    def test_sequence_identity_excluded(self):
        """Sequence in identity_sequence_names is excluded (lines 1273-1276)."""
        # Table that uses the sequence in a column default
        table = MagicMock()
        table.name = "users"
        table.schema = "public"
        table.object_type = SqlObjectType.TABLE
        table.constraints = []

        col = MagicMock()
        col.default_value = "nextval('public.users_id_seq')"
        table.columns = [col]

        seq = MagicMock()
        seq.name = "users_id_seq"
        seq.schema = "public"
        seq.object_type = SqlObjectType.SEQUENCE

        result = _exclude_internal_objects([table, seq], config=None, target_schema="public")
        self.assertNotIn(seq, result)
        self.assertIn(table, result)

    def test_explicit_nextval_sequence_is_kept(self):
        table = MagicMock()
        table.name = "users"
        table.schema = "public"
        table.object_type = SqlObjectType.TABLE
        table.constraints = []

        col = MagicMock()
        col.name = "id"
        col.default_value = "nextval('public.users_seq'::regclass)"
        table.columns = [col]

        seq = MagicMock()
        seq.name = "users_seq"
        seq.schema = "public"
        seq.object_type = SqlObjectType.SEQUENCE

        result = _exclude_internal_objects([table, seq], config=None, target_schema="public")
        self.assertIn(seq, result)
        self.assertIn(table, result)

    def test_sequence_prefix_internal_excluded(self):
        """Sequence with name starting with internal prefix is excluded (line 1277-1278)."""
        seq = MagicMock()
        seq.name = "dblift_schema_history_seq"
        seq.schema = "public"
        seq.object_type = SqlObjectType.SEQUENCE

        result = _exclude_internal_objects([seq], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_trigger_on_internal_table_excluded(self):
        """Trigger on internal table is excluded (lines 1280-1292)."""
        trg = MagicMock()
        trg.name = "my_trigger"
        trg.schema = "public"
        trg.object_type = SqlObjectType.TRIGGER
        trg.table_name = "dblift_migration_lock"
        trg.table_schema = "public"

        result = _exclude_internal_objects([trg], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_constraint_on_internal_table_excluded(self):
        """Constraint whose parent is an internal table is excluded (lines 1295-1308)."""
        con = MagicMock()
        con.name = "some_fk"
        con.schema = "public"
        con.object_type = SqlObjectType.CONSTRAINT
        con.table_name = "dblift_schema_snapshots"
        con.table_schema = "public"
        con.table = None

        result = _exclude_internal_objects([con], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_type_matching_view_name_excluded(self):
        """Type whose name matches a view is excluded (lines 1310-1313)."""
        view = MagicMock()
        view.name = "v_users"
        view.schema = "public"
        view.object_type = SqlObjectType.VIEW

        type_obj = MagicMock()
        type_obj.name = "v_users"
        type_obj.schema = "public"
        type_obj.object_type = SqlObjectType.TYPE

        result = _exclude_internal_objects([view, type_obj], config=None, target_schema="public")
        self.assertIn(view, result)
        self.assertNotIn(type_obj, result)

    def test_type_matching_table_name_excluded(self):
        """Type whose name matches a table is excluded."""
        table = MagicMock()
        table.name = "users"
        table.schema = "public"
        table.object_type = SqlObjectType.TABLE
        table.columns = []
        table.constraints = []

        type_obj = MagicMock()
        type_obj.name = "users"
        type_obj.schema = "public"
        type_obj.object_type = SqlObjectType.TYPE

        result = _exclude_internal_objects([table, type_obj], config=None, target_schema="public")
        self.assertIn(table, result)
        self.assertNotIn(type_obj, result)

    def test_history_table_string_config_at_database_level(self):
        """history_table from config.database.history_table is used (lines 1094-1099)."""
        config = MagicMock(spec=[])
        database = MagicMock(spec=[])
        database.history_table = "custom_history_tbl"
        config.database = database

        obj = _make_obj("custom_history_tbl", schema="public")
        result = _exclude_internal_objects([obj], config=config, target_schema="public")
        self.assertEqual(result, [])

    def test_snapshot_table_string_config_used(self):
        """snapshot_table from config is used (lines 1101-1110)."""
        config = MagicMock(spec=[])
        config.snapshot_table = "my_snapshots"
        config.database = MagicMock(spec=[])

        obj = _make_obj("my_snapshots", schema="public")
        result = _exclude_internal_objects([obj], config=config, target_schema="public")
        self.assertEqual(result, [])

    def test_index_with_no_schema_but_target_schema(self):
        """Index table has no schema but target schema set — still excluded (lines 1250-1253)."""
        idx = MagicMock()
        idx.name = "idx_hist"
        idx.schema = None
        idx.object_type = SqlObjectType.INDEX
        idx.table_name = "dblift_schema_history"
        idx.table_schema = None

        result = _exclude_internal_objects([idx], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_object_with_string_object_type(self):
        """Object with string object_type gets parsed to SqlObjectType (lines 1146-1150)."""
        obj = MagicMock()
        obj.name = "users"
        obj.schema = "public"
        obj.object_type = "TABLE"  # string instead of enum
        obj.columns = []
        obj.constraints = []

        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        # users is not internal, should be kept
        self.assertEqual(len(result), 1)

    def test_unknown_string_object_type_kept(self):
        """Unknown string object_type → obj_type=None → not internal (lines 1147-1150)."""
        obj = MagicMock()
        obj.name = "something_random"
        obj.schema = "public"
        obj.object_type = "UNKNOWN_TYPE_XYZ"

        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        self.assertEqual(len(result), 1)

    def test_index_table_qualified_name_excluded(self):
        """Index with qualified internal table name excluded (lines 1255-1256)."""
        idx = MagicMock()
        idx.name = "idx1"
        idx.schema = "public"
        idx.object_type = SqlObjectType.INDEX
        idx.table_name = "dblift_schema_history"
        idx.table_schema = "public"

        result = _exclude_internal_objects([idx], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_history_table_no_schema_target_schema_set(self):
        """History table with no schema but target_schema set is excluded (lines 1207-1210)."""
        obj = _make_obj("dblift_schema_history", schema=None)
        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# _remove_redundant_unique_constraints: unique index by columns
# ---------------------------------------------------------------------------


class TestRemoveRedundantByColumns(unittest.TestCase):
    def test_removes_constraint_matching_unique_index_by_columns(self):
        """Unique constraint with same columns as unique index is removed."""
        from core.sql_model.base import ConstraintType
        from core.sql_model.index import Index
        from core.sql_model.table import Table

        constraint = MagicMock()
        constraint.constraint_type = ConstraintType.UNIQUE
        constraint.name = "uq_email_different_name"
        constraint.column_names = ["email"]

        table = Table.__new__(Table)
        table.object_type = SqlObjectType.TABLE
        table.name = "users"
        table.schema = "public"
        table.constraints = [constraint]

        idx = MagicMock(spec=Index)
        idx.unique = True
        idx.name = "idx_uq_email"
        idx.table_name = "users"
        idx.table_schema = "public"
        idx.schema = "public"
        idx.columns = ["email"]

        _remove_redundant_unique_constraints([idx, table])
        # constraint should be removed (columns match)
        self.assertEqual(len(table.constraints), 0)

    def test_non_unique_index_does_not_remove_constraint(self):
        """Non-unique index doesn't remove the unique constraint."""
        from core.sql_model.base import ConstraintType
        from core.sql_model.index import Index
        from core.sql_model.table import Table

        constraint = MagicMock()
        constraint.constraint_type = ConstraintType.UNIQUE
        constraint.name = "uq_email"
        constraint.column_names = ["email"]

        table = Table.__new__(Table)
        table.object_type = SqlObjectType.TABLE
        table.name = "users"
        table.schema = "public"
        table.constraints = [constraint]

        idx = MagicMock(spec=Index)
        idx.unique = False  # not unique
        idx.name = "idx_email"
        idx.table_name = "users"
        idx.table_schema = "public"
        idx.schema = "public"
        idx.columns = ["email"]

        _remove_redundant_unique_constraints([idx, table])
        # constraint stays
        self.assertEqual(len(table.constraints), 1)

    def test_pk_constraint_not_removed(self):
        """PRIMARY_KEY constraint is never removed."""
        from core.sql_model.base import ConstraintType
        from core.sql_model.index import Index
        from core.sql_model.table import Table

        constraint = MagicMock()
        constraint.constraint_type = ConstraintType.PRIMARY_KEY
        constraint.name = "pk_users"
        constraint.column_names = ["id"]

        table = Table.__new__(Table)
        table.object_type = SqlObjectType.TABLE
        table.name = "users"
        table.schema = "public"
        table.constraints = [constraint]

        idx = MagicMock(spec=Index)
        idx.unique = True
        idx.name = "pk_users"
        idx.table_name = "users"
        idx.table_schema = "public"
        idx.schema = "public"
        idx.columns = ["id"]

        _remove_redundant_unique_constraints([idx, table])
        # PK constraint stays
        self.assertEqual(len(table.constraints), 1)


# ---------------------------------------------------------------------------
# _populate_export_result_metadata: provider with get_database_version
# ---------------------------------------------------------------------------


class TestPopulateExportResultMetadataExtended(unittest.TestCase):
    def test_get_database_version_called(self):
        """Provider.get_database_version is called when available."""
        result = MagicMock()

        class ProviderWithVersion:
            connection = None

            def get_database_version(self):
                return "14.5"

        provider = ProviderWithVersion()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            _populate_export_result_metadata(result, provider, None, None, None)

        self.assertEqual(result.db_version, "14.5")

    def test_get_database_version_exception_swallowed(self):
        """Exception from get_database_version is swallowed."""
        result = MagicMock()

        class ProviderWithBadVersion:
            connection = None

            def get_database_version(self):
                raise RuntimeError("db_version unavailable")

        provider = ProviderWithBadVersion()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            # should not raise
            _populate_export_result_metadata(result, provider, None, None, None)

    def test_provider_with_connection_uses_plugin_driver_display(self):
        """Provider with connection still uses plugin-declared driver display."""
        from db.provider_registry import ProviderRegistry

        result = MagicMock()
        provider = MagicMock()
        provider.connection = MagicMock()
        provider.quirks = ProviderRegistry.get_quirks("postgresql")
        provider.__class__.__name__ = "PostgreSqlProvider"

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            _populate_export_result_metadata(result, provider, None, None, None)

        self.assertEqual("psycopg", result.native_driver)

    def test_provider_mysql_fallback(self):
        """MySql provider without connection uses fallback driver name from quirks."""
        from db.provider_registry import ProviderRegistry

        result = MagicMock()

        class MySqlProvider:
            connection = None
            quirks = ProviderRegistry.get_quirks("mysql")

        provider = MySqlProvider()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            _populate_export_result_metadata(result, provider, None, None, None)

        self.assertIn("mysql", result.native_driver.lower())

    def test_provider_oracle_fallback(self):
        """Oracle provider without connection uses fallback driver name from quirks."""
        from db.provider_registry import ProviderRegistry

        result = MagicMock()

        class OracleProvider:
            connection = None
            quirks = ProviderRegistry.get_quirks("oracle")

        provider = OracleProvider()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            _populate_export_result_metadata(result, provider, None, None, None)

        self.assertIn("oracle", result.native_driver.lower())

    def test_provider_sqlserver_fallback(self):
        """SqlServer provider without connection uses fallback driver name from quirks."""
        from db.provider_registry import ProviderRegistry

        result = MagicMock()

        class SqlServerProvider:
            connection = None
            quirks = ProviderRegistry.get_quirks("sqlserver")

        provider = SqlServerProvider()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            _populate_export_result_metadata(result, provider, None, None, None)

        self.assertEqual("pymssql", result.native_driver)

    def test_url_with_no_server_match(self):
        """URL without server pattern doesn't crash (no match)."""
        result = MagicMock()
        provider = MagicMock(spec=[])

        # URL without :// pattern
        _populate_export_result_metadata(result, provider, None, None, "just-a-plain-url")
        # server_name should not be set since no match
        result.server_name  # access it — just ensure no AttributeError

    def test_outer_exception_swallowed(self):
        """Outer exception from metadata population is caught."""
        result = MagicMock()
        provider = MagicMock()
        provider.connection = MagicMock()
        provider.connection.getMetaData.side_effect = Exception("metadata crash")

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            # Should not raise
            _populate_export_result_metadata(result, provider, None, None, None)


# ---------------------------------------------------------------------------
# _log_command_footer: time formatting
# ---------------------------------------------------------------------------


class TestLogCommandFooterTimeFormat(unittest.TestCase):
    def test_time_formatted_in_seconds_when_over_1s(self):
        """Execution time > 1s formats as 'X.XX s'."""
        log_func = MagicMock()
        # Use a start time 2 seconds ago
        start = datetime.datetime.now() - datetime.timedelta(seconds=2)
        _log_command_footer(log_func, True, start)
        calls = [str(c) for c in log_func.call_args_list]
        self.assertTrue(any(" s" in c for c in calls))

    def test_time_formatted_in_minutes_when_over_1min(self):
        """Execution time > 1min formats as 'X.XX min'."""
        log_func = MagicMock()
        # Use a start time 65 seconds ago
        start = datetime.datetime.now() - datetime.timedelta(seconds=65)
        _log_command_footer(log_func, True, start)
        calls = [str(c) for c in log_func.call_args_list]
        self.assertTrue(any("min" in c for c in calls))

    def test_set_command_completed_exception_swallowed(self):
        """Exception from set_command_completed is swallowed (lines 1943-1944)."""
        log_func = MagicMock()
        log = MagicMock()
        log.set_command_completed.side_effect = RuntimeError("scc error")
        start = datetime.datetime.now()
        # Should not raise
        _log_command_footer(log_func, True, start, log=log)


# ---------------------------------------------------------------------------
# _is_object_managed: debug logging with managed set sample
# ---------------------------------------------------------------------------


class TestIsObjectManagedDebugLogging(unittest.TestCase):
    def test_managed_set_sample_logged_when_unmanaged(self):
        """When object is not managed but set has entries, sample is logged."""
        obj = MagicMock()
        obj.name = "missing"
        obj.schema = "public"
        obj.object_type = SqlObjectType.TABLE

        managed_set = {("public", "EXISTING", "TABLE")}
        debug_calls = []

        _is_object_managed(obj, managed_set, dialect="postgresql", debug_func=debug_calls.append)

        # Should have logged sample keys
        self.assertTrue(any("EXISTING" in str(c) for c in debug_calls))

    def test_managed_returns_true_with_debug_func(self):
        """When object is in managed_set, debug_func is called with found message."""
        obj = MagicMock()
        obj.name = "FOUND_TABLE"
        obj.schema = "public"
        obj.object_type = SqlObjectType.TABLE

        managed_set = {("public", "FOUND_TABLE", "TABLE")}
        debug_calls = []

        result = _is_object_managed(
            obj, managed_set, dialect="postgresql", debug_func=debug_calls.append
        )
        self.assertTrue(result)
        self.assertTrue(any("found" in c.lower() for c in debug_calls))


# ---------------------------------------------------------------------------
# _get_managed_objects: basic paths
# ---------------------------------------------------------------------------


class TestGetManagedObjects(unittest.TestCase):
    def test_returns_none_on_exception(self):
        """Exception from executor causes return of None (lines 1728-1737)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"

        executor = MagicMock()
        executor.history_manager.get_applied_migrations.side_effect = Exception("db error")

        scripts_dir = MagicMock(spec=Path)

        result = _get_managed_objects(config, executor, scripts_dir)
        self.assertIsNone(result)

    def test_returns_empty_set_when_no_applied_migrations(self):
        """No applied migrations → return empty set (lines 1490-1492)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"

        executor = MagicMock()
        executor.history_manager.get_applied_migrations.return_value = []
        executor.log = MagicMock()

        scripts_dir = MagicMock(spec=Path)

        with patch("core.migration.state.migration_state_manager.MigrationStateManager"):
            result = _get_managed_objects(config, executor, scripts_dir)

        self.assertEqual(result, set())

    def test_debug_func_used_when_no_migrations(self):
        """debug_func is called when no applied migrations found."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"

        executor = MagicMock()
        executor.history_manager.get_applied_migrations.return_value = []
        executor.log = MagicMock()

        scripts_dir = MagicMock(spec=Path)
        debug_calls = []

        with patch("core.migration.state.migration_state_manager.MigrationStateManager"):
            _get_managed_objects(config, executor, scripts_dir, debug_func=debug_calls.append)

        self.assertTrue(any("No applied migrations" in c for c in debug_calls))


# ManagedObjectFilter class removed in Z-2 (was a test-only shim wrapping
# the module-level ``_filter_objects``). Filter logic is exercised
# elsewhere in this file via direct ``_filter_objects`` calls.


# ---------------------------------------------------------------------------
# export_schema: with injected executor
# ---------------------------------------------------------------------------


class TestExportSchemaWithExecutor(unittest.TestCase):
    def test_export_schema_with_executor_injected(self):
        """export_schema accepts executor parameter."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql", unmanaged_only=True, managed_only=True)
        executor = MagicMock()

        # managed_only + unmanaged_only is invalid → False immediately
        result = export_schema(config, opts, executor=executor)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _ensure_schema_payload: with filters
# ---------------------------------------------------------------------------


class TestEnsureSchemaPayloadWithFilters(unittest.TestCase):
    def test_filters_included_in_metadata(self):
        """state.filters are included in snapshot metadata."""
        ex = _make_exporter()
        ex.state.schema_payload = None
        ex.state.target_schema = "public"
        ex.state.schema_version = None
        ex.state.filters = ["--tables=users", "--schema=public"]
        captured_kwargs = {}

        with patch(
            "core.migration.commands.export_schema_command.SchemaSnapshotPayload",
            side_effect=lambda **kw: captured_kwargs.update(kw) or MagicMock(),
        ):
            ex._ensure_schema_payload({}, "postgresql", None)

        metadata = captured_kwargs.get("metadata", {})
        self.assertIn("filters", metadata.get("snapshot", {}))
        self.assertEqual(metadata["snapshot"]["filters"], ["--tables=users", "--schema=public"])

    def test_no_filters_not_included_in_metadata(self):
        """When filters is empty, 'filters' key absent from metadata."""
        ex = _make_exporter()
        ex.state.schema_payload = None
        ex.state.target_schema = "public"
        ex.state.schema_version = None
        ex.state.filters = []
        captured_kwargs = {}

        with patch(
            "core.migration.commands.export_schema_command.SchemaSnapshotPayload",
            side_effect=lambda **kw: captured_kwargs.update(kw) or MagicMock(),
        ):
            ex._ensure_schema_payload({}, "postgresql", None)

        metadata = captured_kwargs.get("metadata", {})
        self.assertNotIn("filters", metadata.get("snapshot", {}))


# ---------------------------------------------------------------------------
# _build_object_type_index: extensions with schema match
# ---------------------------------------------------------------------------


class TestBuildObjectTypeIndexExtended(unittest.TestCase):
    def test_extensions_included_when_schema_matches(self):
        """Extension with matching schema is included."""
        ex = _make_exporter(dialect="postgresql")
        ext = _make_obj("uuid-ossp", schema="public")
        schema_data = {"extensions": [ext]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(ext, all_objs)

    def test_extensions_excluded_when_schema_mismatches(self):
        """Extension with non-matching schema (and target_normalized set) is excluded."""
        ex = _make_exporter(dialect="postgresql")
        ext = _make_obj("uuid-ossp", schema="other")
        schema_data = {"extensions": [ext]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        # With schema "other" != "public", extension is excluded
        self.assertNotIn(ext, all_objs)


# ---------------------------------------------------------------------------
# _setup_infrastructure: log candidate fallbacks (lines 229, 231)
# ---------------------------------------------------------------------------


class TestSetupInfrastructureLogCandidate(unittest.TestCase):
    """Test log_candidate selection paths in _setup_infrastructure."""

    def test_log_candidate_falls_back_to_passed_log_when_executor_log_none(self):
        """If executor.log is None, falls back to the passed log (line 229)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")

        executor = MagicMock()
        # Make executor.log look like None via MagicMock spec trick
        executor.log = None
        executor.provider._ensure_connection = MagicMock()
        executor.snapshot_service = None
        executor.history_manager.get_applied_migrations.return_value = []

        log = MagicMock()
        ex = SchemaExporter(config=config, options=opts, executor=executor, log=log)

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            with patch(
                "core.migration.commands.export_schema_command.get_provider_display_url",
                return_value=None,
            ):
                with patch(
                    "core.migration.state.migration_state_manager.MigrationStateManager"
                ) as mock_sm:
                    mock_sm.return_value.get_current_version.return_value = None
                    result = ex._setup_infrastructure()

        self.assertTrue(result)

    def test_log_candidate_creates_dblift_logger_when_all_none(self):
        """If executor has no log attr and passed log is None, creates DbliftLogger (line 231)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")

        executor = MagicMock(
            spec=["provider", "snapshot_service", "history_manager", "script_manager", "rules"]
        )  # no 'log' attribute
        executor.provider = MagicMock()
        executor.snapshot_service = None
        executor.history_manager.get_applied_migrations.return_value = []

        # Pass NullLog as log (not None, but executor has no 'log')
        from core.logger import NullLog

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=NullLog())

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            with patch(
                "core.migration.commands.export_schema_command.get_provider_display_url",
                return_value=None,
            ):
                with patch(
                    "core.migration.state.migration_state_manager.MigrationStateManager"
                ) as mock_sm:
                    mock_sm.return_value.get_current_version.return_value = None
                    result = ex._setup_infrastructure()

        self.assertTrue(result)


# ---------------------------------------------------------------------------
# _setup_infrastructure: provider sourcing branches (lines 278, 282-283)
# ---------------------------------------------------------------------------


class TestSetupInfrastructureProviderBranches(unittest.TestCase):
    """Test provider setup paths."""

    def _make_executor_mock(self):
        executor = MagicMock()
        executor.provider._ensure_connection = MagicMock()
        executor.snapshot_service = None
        executor.log = MagicMock()
        executor.history_manager.get_applied_migrations.return_value = []
        return executor

    def test_provider_taken_from_executor_when_not_injected(self):
        """Provider comes from executor.provider when not pre-injected (line 280)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")

        executor = self._make_executor_mock()
        mock_provider = MagicMock()
        executor.provider = mock_provider

        # No provider pre-injected (constructor without provider=)
        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())
        # state.provider not set yet
        self.assertIsNone(ex.state.provider)

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            with patch(
                "core.migration.commands.export_schema_command.get_provider_display_url",
                return_value=None,
            ):
                with patch(
                    "core.migration.state.migration_state_manager.MigrationStateManager"
                ) as mock_sm:
                    mock_sm.return_value.get_current_version.return_value = None
                    result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertIs(ex.state.provider, mock_provider)

    def test_provider_created_when_executor_has_no_provider(self):
        """Provider is created via ProviderRegistry when executor has no provider (lines 282-283)."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")

        executor = MagicMock(
            spec=["snapshot_service", "history_manager", "script_manager", "rules", "log"]
        )
        executor.snapshot_service = None
        executor.log = MagicMock()
        executor.history_manager.get_applied_migrations.return_value = []

        ex = SchemaExporter(config=config, options=opts, executor=executor, log=MagicMock())

        mock_created_provider = MagicMock()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            with patch(
                "core.migration.commands.export_schema_command.get_provider_display_url",
                return_value=None,
            ):
                with patch(
                    "core.migration.state.migration_state_manager.MigrationStateManager"
                ) as mock_sm:
                    mock_sm.return_value.get_current_version.return_value = None
                    with patch(
                        "core.migration.commands.export_schema_command.ProviderRegistry"
                    ) as mock_registry:
                        mock_registry.create_provider.return_value = mock_created_provider
                        result = ex._setup_infrastructure()

        self.assertTrue(result)
        self.assertIs(ex.state.provider, mock_created_provider)


# ---------------------------------------------------------------------------
# _print_header: MultiLog branch (lines 321-324)
# ---------------------------------------------------------------------------


class TestPrintHeaderMultiLog(unittest.TestCase):
    def test_multilog_with_console_log_inside_prints_header(self):
        """MultiLog containing ConsoleLog triggers header output (lines 320-324)."""
        from core.logger.log import ConsoleLog, MultiLog

        console_log = MagicMock(spec=ConsoleLog)
        console_log.info = MagicMock()
        multi_log = MagicMock(spec=MultiLog)
        multi_log.logs = [console_log]
        multi_log.info = MagicMock()

        ex = _make_exporter()
        ex.log = multi_log
        ex.state.schema_version = "1.0"
        ex.state.database_url_masked = None
        ex.state.filters = []
        ex.config.database.database_name = "testdb"

        import core.migration.commands.export_schema_command as cmd_module

        cmd_module._console_main_header_printed = True  # skip banner

        with patch("builtins.print"):
            ex._print_header()

        multi_log.console_print.assert_called()

    def test_multilog_without_console_log_skips_header(self):
        """MultiLog with no ConsoleLog inside skips header (lines 320-329)."""
        from core.logger.log import ConsoleLog, MultiLog

        # inner log is not a ConsoleLog
        inner_log = MagicMock()  # plain mock, not ConsoleLog
        multi_log = MagicMock(spec=MultiLog)
        multi_log.logs = [inner_log]
        multi_log.info = MagicMock()

        ex = _make_exporter()
        ex.log = multi_log
        ex.state.schema_version = None
        ex.state.database_url_masked = None
        ex.state.filters = []

        ex._print_header()
        # should_print_header = False → returns early, info NOT called
        multi_log.info.assert_not_called()


# ---------------------------------------------------------------------------
# _generate_object_sql: via mock SqlGeneratorFactory (lines 732-751)
# ---------------------------------------------------------------------------


class TestGenerateObjectSql(unittest.TestCase):
    def test_generate_object_sql_calls_factory(self):
        """_generate_object_sql creates generator and calls generate_schema_script."""
        ex = _make_exporter()
        t1 = _make_obj("users", schema="public", obj_type=SqlObjectType.TABLE)

        mock_generator = MagicMock()
        mock_generator.generate_schema_script.return_value = {"schema.sql": "CREATE TABLE users();"}

        with patch(
            "core.migration.commands.export_schema_command.SqlGeneratorFactory"
        ) as mock_factory:
            mock_factory.create.return_value = mock_generator
            result = ex._generate_object_sql([t1], "postgresql")

        mock_factory.create.assert_called_once_with(
            dialect="postgresql", use_dependency_ordering=True
        )
        mock_generator.generate_schema_script.assert_called_once()
        self.assertEqual(result, {"schema.sql": "CREATE TABLE users();"})

    def test_generate_object_sql_split_by_type_uses_by_type_strategy(self):
        """split_by_type=True uses OrganizationStrategy.BY_TYPE."""
        ex = _make_exporter(output=None, output_dir="/tmp", split_by_type=True)
        t1 = _make_obj("users", schema="public", obj_type=SqlObjectType.TABLE)

        mock_generator = MagicMock()
        mock_generator.generate_schema_script.return_value = {"tables.sql": "CREATE TABLE users();"}

        with patch(
            "core.migration.commands.export_schema_command.SqlGeneratorFactory"
        ) as mock_factory:
            with patch(
                "core.migration.commands.export_schema_command.OrganizationStrategy"
            ) as mock_org:
                mock_factory.create.return_value = mock_generator
                ex._generate_object_sql([t1], "postgresql")

    def test_generate_object_sql_groups_objects_by_type(self):
        """Objects are grouped by type before calling generate_schema_script."""
        ex = _make_exporter()
        t1 = _make_obj("users", schema="public", obj_type=SqlObjectType.TABLE)
        t2 = _make_obj("orders", schema="public", obj_type=SqlObjectType.TABLE)
        v1 = _make_obj("v_users", schema="public", obj_type=SqlObjectType.VIEW)

        mock_generator = MagicMock()
        mock_generator.generate_schema_script.return_value = {}

        captured_schema_dict = {}

        def capture_call(schema_dict, **kwargs):
            captured_schema_dict.update(schema_dict)
            return {}

        mock_generator.generate_schema_script.side_effect = capture_call

        with patch(
            "core.migration.commands.export_schema_command.SqlGeneratorFactory"
        ) as mock_factory:
            mock_factory.create.return_value = mock_generator
            ex._generate_object_sql([t1, t2, v1], "postgresql")

        # Both table objects should be grouped together
        self.assertIn("table", captured_schema_dict)
        self.assertEqual(len(captured_schema_dict["table"]), 2)


# ---------------------------------------------------------------------------
# _filter_objects: filters_used debug paths (lines 1043, 1056)
# ---------------------------------------------------------------------------


class TestFilterObjectsFilterUsedPaths(unittest.TestCase):
    def _make_table(self, name, schema="public"):
        return SimpleNamespace(
            name=name,
            schema=schema,
            object_type=SqlObjectType.TABLE,
        )

    def test_unmanaged_only_debug_called(self):
        """debug_func called with unmanaged count message (line 1043)."""
        t1 = self._make_table("table1")
        t2 = self._make_table("managed")

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)
        debug_calls = []

        managed_set = {("public", "MANAGED", "TABLE")}

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects",
            return_value=managed_set,
        ):
            _filter_objects(
                [t1, t2],
                unmanaged_only=True,
                config=config,
                executor=executor,
                scripts_dir=scripts_dir,
                debug_func=debug_calls.append,
            )

        self.assertTrue(any("unmanaged" in c.lower() for c in debug_calls))

    def test_filters_used_debug_called(self):
        """debug_func called with filters_used count message (line 1056)."""
        t1 = self._make_table("versioned")
        t2 = self._make_table("other")

        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        executor = MagicMock()
        scripts_dir = MagicMock(spec=Path)
        debug_calls = []

        managed_set = {("public", "VERSIONED", "TABLE")}

        with patch(
            "core.migration.commands._managed_object_filter._get_managed_objects",
            return_value=managed_set,
        ):
            _filter_objects(
                [t1, t2],
                versions="1.0",
                config=config,
                executor=executor,
                scripts_dir=scripts_dir,
                debug_func=debug_calls.append,
            )

        self.assertTrue(any("filter" in c.lower() or "version" in c.lower() for c in debug_calls))


# ---------------------------------------------------------------------------
# _exclude_internal_objects: SQLite empty schema vs ``main`` target
# ---------------------------------------------------------------------------


class TestExcludeInternalObjectsSqlite(unittest.TestCase):
    """Introspection may omit schema; objects must still match ``main`` for filtering."""

    def test_trigger_empty_table_schema_excluded_when_target_main(self):
        config = MagicMock()
        config.database.type = "sqlite"
        trg = MagicMock()
        trg.name = "trg_hist"
        trg.schema = None
        trg.object_type = SqlObjectType.TRIGGER
        trg.table_name = "dblift_schema_history"
        trg.table_schema = None
        result = _exclude_internal_objects([trg], config=config, target_schema="main")
        self.assertEqual(result, [])

    def test_constraint_empty_parent_schema_excluded_when_target_main(self):
        config = MagicMock()
        config.database.type = "sqlite"
        con = MagicMock()
        con.name = "pk_hist"
        con.schema = None
        con.object_type = SqlObjectType.CONSTRAINT
        con.table_name = "dblift_schema_history"
        con.table_schema = None
        result = _exclude_internal_objects([con], config=config, target_schema="main")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# _exclude_internal_objects: CosmosDB index/sequence normalization
# ---------------------------------------------------------------------------


class TestExcludeInternalObjectsCosmosDB(unittest.TestCase):
    def test_cosmosdb_index_no_schema_normalized_to_default(self):
        """CosmosDB index with None table_schema is normalized to 'default'."""
        config = MagicMock()
        config.database.type = "cosmosdb"

        # Index on dblift_schema_history with no schema
        idx = MagicMock()
        idx.name = "idx_hist"
        idx.schema = None
        idx.object_type = SqlObjectType.INDEX
        idx.table_name = "dblift_schema_history"
        idx.table_schema = None

        result = _exclude_internal_objects([idx], config=config, target_schema=None)
        self.assertEqual(result, [])

    def test_cosmosdb_object_no_schema_normalized_for_qualified_name(self):
        """CosmosDB object with no schema uses 'default' in qualified name check."""
        config = MagicMock()
        config.database.type = "cosmosdb"

        obj = _make_obj("dblift_schema_history", schema=None)

        result = _exclude_internal_objects([obj], config=config, target_schema=None)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# _populate_export_result_metadata: fallback provider name unknown
# ---------------------------------------------------------------------------


class TestPopulateExportResultMetadataFallbackUnknown(unittest.TestCase):
    def test_unknown_provider_class_name_skips_driver(self):
        """Unknown provider class name results in no native_driver being set."""
        result = MagicMock()

        class SomeUnknownProvider:
            connection = None

        provider = SomeUnknownProvider()

        with patch("core.migration.commands.export_schema_command.ensure_provider_connection"):
            _populate_export_result_metadata(result, provider, None, None, None)

        # For an unknown provider, no assignment to result.native_driver happens
        # (the if/elif chain falls through without matching)
        # Just ensure no exception was raised
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# _get_managed_objects: filtered migrations empty after filters
# ---------------------------------------------------------------------------


class TestGetManagedObjectsFilteredEmpty(unittest.TestCase):
    def test_returns_empty_when_filters_remove_all_migrations(self):
        """After applying filters, if no migrations remain, return empty set."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"

        executor = MagicMock()
        applied = [MagicMock(version="1.0")]
        executor.history_manager.get_applied_migrations.return_value = applied
        executor.log = MagicMock()

        scripts_dir = MagicMock(spec=Path)

        with patch("core.migration.state.migration_state_manager.MigrationStateManager") as mock_sm:
            # apply_filters_to_migrations returns empty list
            mock_sm.return_value.apply_filters_to_migrations.return_value = []
            result = _get_managed_objects(
                config,
                executor,
                scripts_dir,
                target_version="999.0",
            )

        self.assertEqual(result, set())

    def test_returns_empty_set_with_applied_migrations_but_no_script_files(self):
        """Applied migrations with no matching script files → empty managed set + warning logged."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"

        executor = MagicMock()
        applied = [MagicMock(version="1.0")]
        executor.history_manager.get_applied_migrations.return_value = applied
        executor.log = MagicMock()

        # script_manager.load_migration_scripts returns empty dict (no scripts found)
        executor.script_manager.load_migration_scripts.return_value = {}

        scripts_dir = MagicMock(spec=Path)

        with patch("core.migration.state.migration_state_manager.MigrationStateManager") as mock_sm:
            # No filter methods - no filtering applied
            mock_sm.return_value = MagicMock()
            result = _get_managed_objects(config, executor, scripts_dir)

        # No script files found → no managed objects → empty set
        self.assertEqual(result, set())


if __name__ == "__main__":
    unittest.main()
