"""Extended unit tests for export_schema_command.py.

Covers previously untested paths to push coverage from ~29% toward 60%+:
  - _validate_options: each validation branch
  - _normalize_identifier
  - _generate_migration_header / _generate_migration_footer
  - _log_command_footer
  - _write_empty_export (output_dir path)
  - _log_and_count_objects
  - _ensure_schema_payload
  - _populate_export_result_metadata
  - _exclude_internal_objects (various object types)
  - _remove_redundant_unique_constraints
  - _is_object_managed
  - _filter_objects (table/type/managed filters)
  - SchemaExporter._schema_matches
  - SchemaExporter._object_key
  - SchemaExporter._build_object_type_index
  - SchemaExporter._introspect_snapshot_objects
  - _filter_objects
  - export_schema convenience wrapper
"""

import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch  # noqa: F401

from core.migration.commands._schema_export_types import (
    ExportExecutionState,
    ExportSchemaOptions,
)
from core.migration.commands.export_schema_command import (
    SchemaExporter,
    _exclude_internal_objects,
    _filter_objects,
    _generate_migration_footer,
    _generate_migration_header,
    _is_object_managed,
    _log_command_footer,
    _normalize_identifier,
    _normalize_schema_for_dialect,
    _populate_export_result_metadata,
    _remove_redundant_unique_constraints,
    export_schema,
)
from core.sql_model.base import SqlObjectType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obj(name, schema=None, obj_type=SqlObjectType.TABLE, **extra):
    """Create a minimal SqlObject-like mock."""
    obj = MagicMock()
    obj.name = name
    obj.schema = schema
    obj.object_type = obj_type
    for k, v in extra.items():
        setattr(obj, k, v)
    return obj


def _make_exporter(dialect="postgresql", output="out.sql", output_dir=None, **opts_kwargs):
    """Build a SchemaExporter with enough state to call methods without live DB."""
    config = MagicMock()
    config.database.type = dialect
    config.database.schema = "public"
    options = ExportSchemaOptions(output=output, output_dir=output_dir, **opts_kwargs)
    exporter = SchemaExporter.__new__(SchemaExporter)
    exporter.config = config
    exporter.options = options
    exporter.log = MagicMock()
    exporter.executor = MagicMock()
    exporter.state = ExportExecutionState()
    exporter.state.dialect = dialect
    exporter.state.target_schema = "public"
    exporter.state.filters = []
    exporter.start_time = datetime.datetime.now()
    return exporter


# ---------------------------------------------------------------------------
# _normalize_identifier
# ---------------------------------------------------------------------------


class TestNormalizeIdentifier(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(_normalize_identifier(None), "")

    def test_empty_returns_empty(self):
        self.assertEqual(_normalize_identifier(""), "")

    def test_whitespace_returns_empty(self):
        self.assertEqual(_normalize_identifier("   "), "")

    def test_strips_double_quotes(self):
        self.assertEqual(_normalize_identifier('"MyTable"'), "mytable")

    def test_strips_square_brackets(self):
        self.assertEqual(_normalize_identifier("[MyTable]"), "mytable")

    def test_strips_backticks(self):
        self.assertEqual(_normalize_identifier("`MyTable`"), "mytable")

    def test_strips_single_quotes(self):
        self.assertEqual(_normalize_identifier("'value'"), "value")

    def test_lowercases(self):
        self.assertEqual(_normalize_identifier("PUBLIC"), "public")

    def test_no_quotes_lowercases(self):
        self.assertEqual(_normalize_identifier("MySchema"), "myschema")


# ---------------------------------------------------------------------------
# _generate_migration_header / _generate_migration_footer
# ---------------------------------------------------------------------------


class TestGenerateMigrationHeader(unittest.TestCase):
    def test_contains_file_name(self):
        header = _generate_migration_header("schema.sql", 5, "postgresql")
        self.assertIn("schema.sql", header)

    def test_contains_object_count(self):
        header = _generate_migration_header("schema.sql", 42, "postgresql")
        self.assertIn("42", header)

    def test_contains_dialect(self):
        header = _generate_migration_header("schema.sql", 0, "mysql")
        self.assertIn("mysql", header)

    def test_custom_description_included(self):
        header = _generate_migration_header("f.sql", 1, "oracle", description="My Export")
        self.assertIn("My Export", header)

    def test_default_description_used_when_none(self):
        header = _generate_migration_header("f.sql", 1, "oracle", description=None)
        self.assertIn("Exported database schema", header)

    def test_mark_as_executed_hint_present(self):
        header = _generate_migration_header("f.sql", 0, "postgresql")
        self.assertIn("mark-as-executed", header)

    def test_sqlserver_session_options_present(self):
        header = _generate_migration_header("f.sql", 1, "sqlserver")
        self.assertIn("SET ANSI_NULLS ON", header)
        self.assertIn("SET QUOTED_IDENTIFIER ON", header)


class TestGenerateMigrationFooter(unittest.TestCase):
    def test_footer_ends_migration(self):
        footer = _generate_migration_footer()
        self.assertIn("End of migration", footer)


# ---------------------------------------------------------------------------
# _log_command_footer
# ---------------------------------------------------------------------------


class TestLogCommandFooter(unittest.TestCase):
    def test_success_message(self):
        log_func = MagicMock()
        start = datetime.datetime.now()
        _log_command_footer(log_func, True, start)
        calls = [str(c) for c in log_func.call_args_list]
        self.assertTrue(any("completed successfully" in c for c in calls))

    def test_failure_message(self):
        log_func = MagicMock()
        start = datetime.datetime.now()
        _log_command_footer(log_func, False, start)
        calls = [str(c) for c in log_func.call_args_list]
        self.assertTrue(any("failed" in c for c in calls))

    def test_calls_set_command_completed_when_log_has_it(self):
        log_func = MagicMock()
        log = MagicMock()
        log.set_command_completed = MagicMock()
        start = datetime.datetime.now()
        _log_command_footer(log_func, True, start, log=log)
        log.set_command_completed.assert_called_once()

    def test_no_error_when_log_has_no_set_command_completed(self):
        log_func = MagicMock()
        log = MagicMock(spec=[])  # no set_command_completed
        start = datetime.datetime.now()
        # Should not raise
        _log_command_footer(log_func, True, start, log=log)


# ---------------------------------------------------------------------------
# _validate_options (via SchemaExporter)
# ---------------------------------------------------------------------------


class TestValidateOptions(unittest.TestCase):
    def _exporter(self, **opts):
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        options = ExportSchemaOptions(**opts)
        ex = SchemaExporter(config=config, options=options)
        return ex

    def test_invalid_source_returns_false(self):
        log = MagicMock()
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        options = ExportSchemaOptions(source="bad-source", output="out.sql")
        ex = SchemaExporter(config=config, options=options, log=log)
        result = ex._validate_options()
        self.assertFalse(result)
        log.error.assert_called()

    def test_valid_source_live_database(self):
        ex = self._exporter(source="live-database", output="out.sql")
        result = ex._validate_options()
        self.assertTrue(result)

    def test_file_model_without_snapshot_model_fails(self):
        ex = self._exporter(source="file-model", output="out.sql")
        result = ex._validate_options()
        self.assertFalse(result)

    def test_file_model_with_nonexistent_snapshot_fails(self):
        ex = self._exporter(
            source="file-model", output="out.sql", snapshot_model="/nonexistent/path.json"
        )
        result = ex._validate_options()
        self.assertFalse(result)

    def test_output_and_output_dir_both_fails(self):
        ex = self._exporter(output="out.sql", output_dir="/tmp")
        result = ex._validate_options()
        self.assertFalse(result)

    def test_split_by_type_without_output_dir_fails(self):
        ex = self._exporter(output="out.sql", split_by_type=True)
        result = ex._validate_options()
        self.assertFalse(result)

    def test_split_by_type_with_output_dir_passes(self):
        ex = self._exporter(output_dir="/tmp", split_by_type=True)
        result = ex._validate_options()
        self.assertTrue(result)

    def test_no_output_no_output_dir_fails(self):
        ex = self._exporter()
        result = ex._validate_options()
        self.assertFalse(result)

    def test_unmanaged_and_managed_conflict_fails(self):
        ex = self._exporter(output="out.sql", unmanaged_only=True, managed_only=True)
        result = ex._validate_options()
        self.assertFalse(result)

    def test_filters_built_for_non_default_source(self):
        ex = self._exporter(source="database-model", output="out.sql")
        ex._validate_options()
        self.assertTrue(any("database-model" in f for f in ex.state.filters))

    def test_tables_filter_added(self):
        ex = self._exporter(output="out.sql", tables="users,orders")
        ex._validate_options()
        self.assertTrue(any("tables" in f for f in ex.state.filters))

    def test_schema_filter_added(self):
        ex = self._exporter(output="out.sql", schema="myschema")
        ex._validate_options()
        self.assertTrue(any("schema" in f for f in ex.state.filters))

    def test_types_filter_added(self):
        ex = self._exporter(output="out.sql", types="table,view")
        ex._validate_options()
        self.assertTrue(any("types" in f for f in ex.state.filters))

    def test_unmanaged_only_filter_added(self):
        ex = self._exporter(output="out.sql", unmanaged_only=True)
        ex._validate_options()
        self.assertTrue(any("unmanaged" in f for f in ex.state.filters))

    def test_managed_only_filter_added(self):
        ex = self._exporter(output="out.sql", managed_only=True)
        ex._validate_options()
        self.assertTrue(any("managed" in f for f in ex.state.filters))


# ---------------------------------------------------------------------------
# _write_empty_export (output_dir path)
# ---------------------------------------------------------------------------


class TestWriteEmptyExport(unittest.TestCase):
    def test_output_dir_creates_placeholder_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = _make_exporter(output=None, output_dir=tmpdir)
            ex._write_empty_export("postgresql", None)
            placeholder = Path(tmpdir) / "empty_export.sql"
            self.assertTrue(placeholder.exists())
            content = placeholder.read_text(encoding="utf-8")
            self.assertIn("No objects found", content)
            ex.log.info.assert_called()

    def test_output_file_path_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "subdir" / "empty.sql"
            ex = _make_exporter(output=str(out))
            ex._write_empty_export("mysql", "My description")
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("No objects found", content)


# ---------------------------------------------------------------------------
# _log_and_count_objects
# ---------------------------------------------------------------------------


class TestLogAndCountObjects(unittest.TestCase):
    def test_returns_counts_by_type(self):
        ex = _make_exporter()
        t1 = _make_obj("users", obj_type=SqlObjectType.TABLE)
        t2 = _make_obj("orders", obj_type=SqlObjectType.TABLE)
        v1 = _make_obj("v_users", obj_type=SqlObjectType.VIEW)
        counts = ex._log_and_count_objects([t1, t2, v1])
        # counts keys are lowercase type names
        total = sum(counts.values())
        self.assertEqual(total, 3)

    def test_empty_list_returns_empty_counts(self):
        ex = _make_exporter()
        counts = ex._log_and_count_objects([])
        self.assertEqual(counts, {})


# ---------------------------------------------------------------------------
# _ensure_schema_payload
# ---------------------------------------------------------------------------


class TestEnsureSchemaPayload(unittest.TestCase):
    def test_does_not_overwrite_existing_payload(self):
        ex = _make_exporter()
        existing = MagicMock()
        ex.state.schema_payload = existing
        ex._ensure_schema_payload({}, "postgresql", None)
        # payload unchanged
        self.assertIs(ex.state.schema_payload, existing)

    def test_builds_payload_when_none(self):
        ex = _make_exporter()
        ex.state.schema_payload = None
        ex.state.target_schema = "public"
        ex.state.schema_version = None
        with patch(
            "core.migration.commands.export_schema_command.SchemaSnapshotPayload"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            ex._ensure_schema_payload({"tables": [], "views": []}, "postgresql", None)
        mock_cls.assert_called_once()

    def test_includes_schema_version_in_metadata(self):
        ex = _make_exporter()
        ex.state.schema_payload = None
        ex.state.target_schema = "public"
        ex.state.schema_version = "3.0"
        captured_kwargs = {}
        with patch(
            "core.migration.commands.export_schema_command.SchemaSnapshotPayload",
            side_effect=lambda **kw: captured_kwargs.update(kw) or MagicMock(),
        ):
            ex._ensure_schema_payload({}, "postgresql", None)
        metadata = captured_kwargs.get("metadata", {})
        self.assertIn("current_version", metadata.get("migration", {}))

    def test_includes_description_in_metadata(self):
        ex = _make_exporter()
        ex.state.schema_payload = None
        ex.state.target_schema = "public"
        ex.state.schema_version = None
        captured_kwargs = {}
        with patch(
            "core.migration.commands.export_schema_command.SchemaSnapshotPayload",
            side_effect=lambda **kw: captured_kwargs.update(kw) or MagicMock(),
        ):
            ex._ensure_schema_payload({}, "postgresql", "My snapshot")
        metadata = captured_kwargs.get("metadata", {})
        self.assertEqual(metadata.get("snapshot", {}).get("description"), "My snapshot")


# ---------------------------------------------------------------------------
# _populate_export_result_metadata
# ---------------------------------------------------------------------------


class TestPopulateExportResultMetadata(unittest.TestCase):
    def test_sets_schema_version(self):
        result = MagicMock()
        provider = MagicMock(spec=[])
        _populate_export_result_metadata(result, provider, "2.0", None, None)
        self.assertEqual(result.current_schema_version, "2.0")

    def test_sets_database_url_masked(self):
        result = MagicMock()
        provider = MagicMock(spec=[])
        _populate_export_result_metadata(result, provider, None, "postgresql://****@host/db", None)
        self.assertEqual(result.database_url_masked, "postgresql://****@host/db")

    def test_extracts_server_name_from_url(self):
        result = MagicMock()
        provider = MagicMock(spec=[])
        _populate_export_result_metadata(
            result, provider, None, None, "postgresql://myserver:5432/db"
        )
        self.assertEqual(result.server_name, "myserver")

    def test_fallback_server_name_from_masked_url(self):
        result = MagicMock()
        provider = MagicMock(spec=[])
        _populate_export_result_metadata(
            result, provider, None, "postgresql://fallbackhost/db", None
        )
        self.assertEqual(result.server_name, "fallbackhost")

    def test_no_error_when_provider_has_no_get_database_version(self):
        result = MagicMock()
        provider = MagicMock(spec=[])  # no get_database_version
        # Should not raise
        _populate_export_result_metadata(result, provider, None, None, None)

    def test_provider_class_name_used_for_native_driver_cosmos(self):
        from db.provider_registry import ProviderRegistry

        result = MagicMock()

        class CosmosDbProvider:
            connection = None
            quirks = ProviderRegistry.get_quirks("cosmosdb")

        provider = CosmosDbProvider()
        _populate_export_result_metadata(result, provider, None, None, None)
        self.assertEqual(result.native_driver, "Azure Cosmos DB SDK for Python")

    def test_provider_class_name_used_for_native_driver_postgresql(self):
        from db.provider_registry import ProviderRegistry

        result = MagicMock()

        class PostgreSqlProvider:
            connection = None
            quirks = ProviderRegistry.get_quirks("postgresql")

        provider = PostgreSqlProvider()
        _populate_export_result_metadata(result, provider, None, None, None)
        self.assertEqual(result.native_driver, "psycopg")


# ---------------------------------------------------------------------------
# _exclude_internal_objects
# ---------------------------------------------------------------------------


class TestExcludeInternalObjects(unittest.TestCase):
    def test_empty_list_returns_empty(self):
        self.assertEqual(_exclude_internal_objects([]), [])

    def test_removes_history_table(self):
        obj = _make_obj("dblift_schema_history", schema="public")
        config = MagicMock(spec=[])  # no string attributes
        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        # The history table should be excluded
        self.assertEqual(result, [])

    def test_removes_lock_table(self):
        obj = _make_obj("dblift_migration_lock", schema="public")
        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_keeps_non_internal_table(self):
        obj = _make_obj("users", schema="public", obj_type=SqlObjectType.TABLE)
        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        self.assertEqual(len(result), 1)

    def test_removes_index_on_internal_table(self):
        idx = MagicMock()
        idx.name = "dblift_schema_history_pkey"
        idx.schema = "public"
        idx.object_type = SqlObjectType.INDEX
        idx.table_name = "dblift_schema_history"
        idx.table_schema = "public"
        result = _exclude_internal_objects([idx], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_removes_trigger_on_internal_table(self):
        trg = MagicMock()
        trg.name = "history_trigger"
        trg.schema = "public"
        trg.object_type = SqlObjectType.TRIGGER
        trg.table_name = "dblift_schema_history"
        trg.table_schema = "public"
        result = _exclude_internal_objects([trg], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_removes_constraint_on_internal_table(self):
        con = MagicMock()
        con.name = "hist_pk"
        con.schema = "public"
        con.object_type = SqlObjectType.CONSTRAINT
        con.table_name = "dblift_schema_history"
        con.table_schema = "public"
        con.table = None
        result = _exclude_internal_objects([con], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_removes_snapshot_table(self):
        obj = _make_obj("dblift_schema_snapshots", schema="public")
        result = _exclude_internal_objects([obj], config=None, target_schema="public")
        self.assertEqual(result, [])

    def test_custom_history_table_from_string_config(self):
        obj = _make_obj("my_history", schema="public")
        config = MagicMock(spec=[])
        config.history_table = "my_history"
        result = _exclude_internal_objects([obj], config=config, target_schema="public")
        self.assertEqual(result, [])

    def test_non_internal_sequence_kept(self):
        seq = MagicMock()
        seq.name = "user_id_seq"
        seq.schema = "public"
        seq.object_type = SqlObjectType.SEQUENCE
        result = _exclude_internal_objects([seq], config=None, target_schema="public")
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# _remove_redundant_unique_constraints
# ---------------------------------------------------------------------------


class TestRemoveRedundantUniqueConstraints(unittest.TestCase):
    def test_empty_list_no_error(self):
        _remove_redundant_unique_constraints([])  # should not raise

    def test_no_indexes_no_removal(self):
        from core.comparison.diff_models import ConstraintDiff
        from core.sql_model.base import ConstraintType
        from core.sql_model.table import Table

        constraint = MagicMock()
        constraint.constraint_type = ConstraintType.UNIQUE
        constraint.name = "uq_users_email"
        constraint.column_names = ["email"]

        table = MagicMock()
        table.object_type = SqlObjectType.TABLE
        table.name = "users"
        table.schema = "public"
        table.constraints = [constraint]

        _remove_redundant_unique_constraints([table])
        # constraint should remain since no matching index
        self.assertEqual(len(table.constraints), 1)

    def test_removes_unique_constraint_with_matching_index_by_name(self):
        from core.sql_model.base import ConstraintType
        from core.sql_model.index import Index
        from core.sql_model.table import Table

        constraint = MagicMock()
        constraint.constraint_type = ConstraintType.UNIQUE
        constraint.name = "uq_email"
        constraint.column_names = []

        # Must use a real Table instance because the function uses isinstance(obj, Table)
        table = Table.__new__(Table)
        table.object_type = SqlObjectType.TABLE
        table.name = "users"
        table.schema = "public"
        table.constraints = [constraint]

        idx = MagicMock(spec=Index)
        idx.unique = True
        idx.name = "uq_email"
        idx.table_name = "users"
        idx.table_schema = "public"
        idx.schema = "public"
        idx.columns = []

        _remove_redundant_unique_constraints([idx, table])
        # constraint should be removed
        self.assertEqual(len(table.constraints), 0)


# ---------------------------------------------------------------------------
# _is_object_managed
# ---------------------------------------------------------------------------


class TestIsObjectManaged(unittest.TestCase):
    def _make_sql_obj(self, name, schema="public", obj_type=SqlObjectType.TABLE):
        obj = MagicMock()
        obj.name = name
        obj.schema = schema
        obj.object_type = obj_type
        return obj

    def test_managed_object_returns_true(self):
        obj = self._make_sql_obj("users")
        managed_set = {("public", "USERS", "TABLE")}
        result = _is_object_managed(obj, managed_set, dialect="postgresql")
        self.assertTrue(result)

    def test_unmanaged_object_returns_false(self):
        obj = self._make_sql_obj("orders")
        managed_set = {("public", "USERS", "TABLE")}
        result = _is_object_managed(obj, managed_set, dialect="postgresql")
        self.assertFalse(result)

    def test_materialized_view_treated_as_view(self):
        obj = MagicMock()
        obj.name = "mv_sales"
        obj.schema = "public"
        obj.object_type = SqlObjectType.MATERIALIZED_VIEW
        managed_set = {("public", "MV_SALES", "VIEW")}
        result = _is_object_managed(obj, managed_set, dialect="postgresql")
        self.assertTrue(result)

    def test_debug_func_called_for_unmanaged(self):
        obj = self._make_sql_obj("missing")
        managed_set = set()
        debug_calls = []
        _is_object_managed(obj, managed_set, dialect="postgresql", debug_func=debug_calls.append)
        self.assertTrue(len(debug_calls) > 0)

    def test_oracle_schema_uppercased(self):
        obj = MagicMock()
        obj.name = "MY_TABLE"
        obj.schema = "myschema"
        obj.object_type = SqlObjectType.TABLE
        # Oracle normalizes schema to uppercase
        managed_set = {("MYSCHEMA", "MY_TABLE", "TABLE")}
        result = _is_object_managed(obj, managed_set, dialect="oracle")
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# _filter_objects
# ---------------------------------------------------------------------------


class TestFilterObjects(unittest.TestCase):
    def _make_table(self, name, schema="public"):
        # Use SimpleNamespace so hasattr returns False for missing attrs
        obj = SimpleNamespace(name=name, schema=schema, object_type=SqlObjectType.TABLE)
        return obj

    def _make_view(self, name, schema="public"):
        obj = SimpleNamespace(name=name, schema=schema, object_type=SqlObjectType.VIEW)
        return obj

    def test_no_filters_returns_all(self):
        objs = [self._make_table("t1"), self._make_table("t2")]
        result = _filter_objects(objs)
        self.assertEqual(len(result), 2)

    def test_tables_filter_by_name(self):
        t1 = self._make_table("users")
        t2 = self._make_table("orders")
        result = _filter_objects([t1, t2], tables="USERS")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "users")

    def test_tables_filter_case_insensitive(self):
        t1 = self._make_table("Users")
        result = _filter_objects([t1], tables="users")
        self.assertEqual(len(result), 1)

    def test_types_filter_table(self):
        t1 = self._make_table("users")
        v1 = self._make_view("v_users")
        result = _filter_objects([t1, v1], types="table")
        # Only table
        self.assertEqual(len(result), 1)

    def test_types_filter_plural_normalized(self):
        t1 = self._make_table("users")
        v1 = self._make_view("v_users")
        result = _filter_objects([t1, v1], types="tables")
        self.assertEqual(len(result), 1)

    def test_types_filter_view(self):
        t1 = self._make_table("users")
        v1 = self._make_view("v_users")
        result = _filter_objects([t1, v1], types="view")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "v_users")

    def test_managed_only_without_scripts_dir_logs_warning(self):
        t1 = self._make_table("users")
        result = _filter_objects([t1], managed_only=True, config=MagicMock())
        # No scripts_dir → warning logged, objects returned as-is (not None)
        self.assertIsNotNone(result)

    def test_unmanaged_only_without_scripts_dir_logs_warning(self):
        t1 = self._make_table("users")
        result = _filter_objects([t1], unmanaged_only=True, config=MagicMock())
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# SchemaExporter._schema_matches
# ---------------------------------------------------------------------------


class TestSchemaMatches(unittest.TestCase):
    def _exporter_for_postgresql(self):
        return _make_exporter(dialect="postgresql")

    def test_empty_target_accepts_all(self):
        ex = self._exporter_for_postgresql()
        obj = _make_obj("users", schema="public")
        # When target_schema_normalized is empty, accept everything
        self.assertTrue(ex._schema_matches(obj, ""))

    def test_matching_schema_returns_true(self):
        ex = self._exporter_for_postgresql()
        obj = _make_obj("users", schema="public")
        self.assertTrue(ex._schema_matches(obj, "public"))

    def test_non_matching_schema_returns_false(self):
        ex = self._exporter_for_postgresql()
        obj = _make_obj("users", schema="other")
        result = ex._schema_matches(obj, "public")
        self.assertFalse(result)
        ex.log.debug.assert_called()

    def test_oracle_uppercase_match(self):
        config = MagicMock()
        config.database.type = "oracle"
        options = ExportSchemaOptions(output="out.sql")
        ex = SchemaExporter.__new__(SchemaExporter)
        ex.config = config
        ex.options = options
        ex.log = MagicMock()
        ex.state = ExportExecutionState()
        ex.start_time = datetime.datetime.now()
        obj = _make_obj("MY_TABLE", schema="MY_SCHEMA")
        # Oracle normalizes to uppercase
        self.assertTrue(ex._schema_matches(obj, "MY_SCHEMA"))


# ---------------------------------------------------------------------------
# SchemaExporter._object_key
# ---------------------------------------------------------------------------


class TestObjectKey(unittest.TestCase):
    def test_returns_tuple_with_type_schema_name(self):
        ex = _make_exporter()
        obj = MagicMock()
        obj.object_type = SqlObjectType.TABLE
        obj.schema = "public"
        obj.name = "users"
        key = ex._object_key(obj)
        self.assertIsInstance(key, tuple)
        self.assertEqual(len(key), 3)

    def test_normalizes_case(self):
        ex = _make_exporter()
        obj = MagicMock()
        obj.object_type = SqlObjectType.TABLE
        obj.schema = "PUBLIC"
        obj.name = '"Users"'
        key = ex._object_key(obj)
        # schema and name should be normalized (lowercase, no quotes)
        self.assertEqual(key[1], "public")
        self.assertEqual(key[2], "users")


# ---------------------------------------------------------------------------
# SchemaExporter._build_object_type_index
# ---------------------------------------------------------------------------


class TestBuildObjectTypeIndex(unittest.TestCase):
    def _exporter(self):
        return _make_exporter(dialect="postgresql")

    def test_tables_included_with_schema_match(self):
        ex = self._exporter()
        t1 = _make_obj("users", schema="public", obj_type=SqlObjectType.TABLE)
        schema_data = {"tables": [t1]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(t1, all_objs)
        self.assertIn(t1, typed["tables"])

    def test_tables_excluded_with_schema_mismatch(self):
        ex = self._exporter()
        t1 = _make_obj("users", schema="other", obj_type=SqlObjectType.TABLE)
        schema_data = {"tables": [t1]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertNotIn(t1, all_objs)

    def test_materialized_views_merged_into_views(self):
        ex = self._exporter()
        mv = _make_obj("mv_sales", schema="public", obj_type=SqlObjectType.MATERIALIZED_VIEW)
        schema_data = {"materialized_views": [mv]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(mv, all_objs)
        self.assertIn(mv, typed["views"])

    def test_relation_backed_user_defined_types_excluded(self):
        ex = self._exporter()
        mv = _make_obj("mv_sales", schema="public", obj_type=SqlObjectType.MATERIALIZED_VIEW)
        udt = _make_obj("mv_sales", schema="public", obj_type=SqlObjectType.TYPE)
        schema_data = {"materialized_views": [mv], "user_defined_types": [udt]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(mv, all_objs)
        self.assertNotIn(udt, all_objs)
        self.assertNotIn(udt, typed["user_defined_types"])

    def test_indexes_dict_format_processed(self):
        ex = self._exporter()
        idx = MagicMock()
        idx.name = "idx_users"
        idx.schema = "public"
        idx.object_type = SqlObjectType.INDEX
        schema_data = {"indexes": {"users": [idx]}}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(idx, all_objs)

    def test_indexes_list_format_processed(self):
        ex = self._exporter()
        idx = MagicMock()
        idx.name = "idx_users"
        idx.schema = "public"
        idx.object_type = SqlObjectType.INDEX
        schema_data = {"indexes": [idx]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(idx, all_objs)

    def test_global_types_no_schema_filter(self):
        ex = self._exporter()
        fdw = MagicMock()
        fdw.name = "my_fdw"
        fdw.schema = None
        fdw.object_type = "foreign_data_wrapper"
        schema_data = {"foreign_data_wrappers": [fdw]}
        all_objs, typed = ex._build_object_type_index(schema_data, "public")
        self.assertIn(fdw, all_objs)

    def test_extensions_included_when_no_target_schema(self):
        ex = self._exporter()
        ext = MagicMock()
        ext.name = "uuid-ossp"
        ext.schema = None
        ext.object_type = "extension"
        schema_data = {"extensions": [ext]}
        all_objs, typed = ex._build_object_type_index(schema_data, "")
        self.assertIn(ext, all_objs)

    def test_owned_sequences_excluded_but_standalone_sequences_kept(self):
        ex = self._exporter()
        table = _make_obj("users", schema="public", obj_type=SqlObjectType.TABLE)
        owned_seq = _make_obj(
            "users_id_seq",
            schema="public",
            obj_type=SqlObjectType.SEQUENCE,
            owned_by_table="public.users",
            owned_by_column="id",
        )
        standalone_seq = _make_obj("order_seq", schema="public", obj_type=SqlObjectType.SEQUENCE)
        schema_data = {"tables": [table], "sequences": [owned_seq, standalone_seq]}

        all_objs, typed = ex._build_object_type_index(schema_data, "public")

        self.assertIn(table, all_objs)
        self.assertNotIn(owned_seq, all_objs)
        self.assertNotIn(owned_seq, typed["sequences"])
        self.assertIn(standalone_seq, all_objs)
        self.assertIn(standalone_seq, typed["sequences"])

    def test_implicit_owned_sequence_referenced_by_nextval_default_is_excluded(self):
        ex = self._exporter()
        column = MagicMock()
        column.name = "id"
        column.default_value = "nextval('legacy_t_id_seq'::regclass)"
        table = _make_obj(
            "legacy_t",
            schema="public",
            obj_type=SqlObjectType.TABLE,
            columns=[column],
        )
        sequence = _make_obj(
            "legacy_t_id_seq",
            schema="public",
            obj_type=SqlObjectType.SEQUENCE,
            owned_by_table="public.legacy_t",
            owned_by_column="id",
        )

        all_objs, typed = ex._build_object_type_index(
            {"tables": [table], "sequences": [sequence]},
            "public",
        )

        self.assertNotIn(sequence, all_objs)
        self.assertNotIn(sequence, typed["sequences"])

    def test_explicit_sequence_referenced_by_nextval_default_is_kept(self):
        ex = self._exporter()
        column = MagicMock()
        column.name = "id"
        column.default_value = "nextval('orders_seq'::regclass)"
        table = _make_obj(
            "orders",
            schema="public",
            obj_type=SqlObjectType.TABLE,
            columns=[column],
        )
        sequence = _make_obj("orders_seq", schema="public", obj_type=SqlObjectType.SEQUENCE)

        all_objs, typed = ex._build_object_type_index(
            {"tables": [table], "sequences": [sequence]},
            "public",
        )

        self.assertIn(sequence, all_objs)
        self.assertIn(sequence, typed["sequences"])


# ---------------------------------------------------------------------------
# SchemaExporter._introspect_snapshot_objects
# ---------------------------------------------------------------------------


class TestIntrospectSnapshotObjects(unittest.TestCase):
    def test_extracts_all_object_type_keys(self):
        from core.migration.commands._schema_export_types import _OBJECT_TYPE_KEYS

        ex = _make_exporter()
        payload = MagicMock()
        for key in _OBJECT_TYPE_KEYS:
            setattr(payload, key, [])
        payload.tables = [_make_obj("users")]

        all_objs, typed = ex._introspect_snapshot_objects(payload)
        self.assertEqual(len(all_objs), 1)
        self.assertIn("tables", typed)

    def test_handles_none_attributes_gracefully(self):
        from core.migration.commands._schema_export_types import _OBJECT_TYPE_KEYS

        ex = _make_exporter()
        payload = MagicMock()
        # All keys return None
        for key in _OBJECT_TYPE_KEYS:
            setattr(payload, key, None)

        all_objs, typed = ex._introspect_snapshot_objects(payload)
        self.assertEqual(all_objs, [])


# ---------------------------------------------------------------------------
# ManagedObjectFilter class removed in Z-2 (was a test-only shim around
# the module-level ``_filter_objects``). The filter logic is exercised
# elsewhere in this file via direct ``_filter_objects`` calls.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# export_schema convenience function
# ---------------------------------------------------------------------------


class TestExportSchemaConvenienceWrapper(unittest.TestCase):
    def test_returns_false_on_invalid_source(self):
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(source="invalid", output="out.sql")
        result = export_schema(config, opts)
        self.assertFalse(result)

    def test_returns_false_when_no_output(self):
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions()  # no output, no output_dir
        result = export_schema(config, opts)
        self.assertFalse(result)

    def test_provider_injected_to_exporter_state(self):
        """When provider= passed to export_schema, it is stored in state."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        provider = MagicMock()

        captured = {}

        class _CaptureExporter(SchemaExporter):
            def run(self):
                captured["provider"] = self.state.provider
                return False

        with patch(
            "core.migration.commands.export_schema_command.SchemaExporter", _CaptureExporter
        ):
            export_schema(config, opts, provider=provider)

        self.assertIs(captured.get("provider"), provider)

    def test_run_returns_false_on_validate_failure(self):
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql", unmanaged_only=True, managed_only=True)
        result = export_schema(config, opts)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# SchemaExporter.run — exception path
# ---------------------------------------------------------------------------


class TestSchemaExporterRunExceptionPath(unittest.TestCase):
    def test_run_returns_false_on_unexpected_exception(self):
        """An unhandled exception in _setup_infrastructure returns False."""
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        ex = SchemaExporter(config=config, options=opts)

        def _bad_setup():
            raise RuntimeError("simulated crash")

        ex._validate_options = lambda: True
        ex._setup_infrastructure = _bad_setup  # type: ignore[method-assign]
        result = ex.run()
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# SchemaExporter._print_main_banner — BUG-04 banner ordering
# ---------------------------------------------------------------------------


class TestPrintMainBanner(unittest.TestCase):
    def _make_exporter(self, log=None):
        config = MagicMock()
        config.database.type = "postgresql"
        config.database.schema = "public"
        opts = ExportSchemaOptions(output="out.sql")
        return SchemaExporter(config=config, options=opts, log=log)

    def test_banner_printed_before_validation_error(self):
        """_print_main_banner is called inside run() before _validate_options."""
        ex = self._make_exporter()
        call_order = []

        ex._print_main_banner = lambda: call_order.append("banner")
        ex._validate_options = lambda: (call_order.append("validate"), False)[1]
        ex._setup_infrastructure = lambda: True

        ex.run()
        self.assertEqual(call_order[0], "banner", "banner must appear before validate")
        self.assertIn("validate", call_order)

    def test_print_main_banner_no_op_for_null_log(self):
        """NullLog: _print_main_banner must not raise."""
        from core.logger import NullLog

        ex = self._make_exporter(log=NullLog())
        ex._print_main_banner()  # should not raise

    def test_print_main_banner_no_op_for_non_console_log(self):
        """Non-console log: banner is skipped (no ConsoleLog in chain)."""
        ex = self._make_exporter(log=MagicMock())
        ex._print_main_banner()  # should not raise


if __name__ == "__main__":
    unittest.main()
