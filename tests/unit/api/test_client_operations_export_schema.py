"""Tests for ``api/_client_operations.export_schema_operation`` (PR-D4).

The pre-existing ``test_export_schema_options_parameter.py`` exercises
the public ``DBLiftClient.export_schema`` surface (BUG-03 regression).
This file targets the **private operation function** that lives in
``api/_client_operations.py`` so the per-kwarg → ``ExportSchemaOptions``
translation, the precedence rule, and the error path are pinned
independently of the public method's signature drift.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _make_client(*, additional_dirs=None, recursive=True):
    """Minimal client stub — only the attributes the operation reads."""
    migrations = SimpleNamespace(
        directories=additional_dirs or [],
        recursive=recursive,
    )
    config = SimpleNamespace(migrations=migrations)
    events = MagicMock(name="events")
    client = SimpleNamespace(
        config=config,
        executor=MagicMock(name="executor"),
        logger=MagicMock(name="logger"),
        provider=MagicMock(name="provider"),
        events=events,
        _get_scripts_dir=MagicMock(return_value=Path("/tmp/scripts")),
    )
    return client


class TestBuildExportSchemaOptions:
    def test_string_kwargs_passthrough(self):
        from api._client_operations import _build_export_schema_options

        client = _make_client()
        opts = _build_export_schema_options(
            client,
            output="/tmp/out.sql",
            output_dir=None,
            split_by_type=False,
            tables=None,
            types=None,
            unmanaged_only=False,
            managed_only=False,
            include_drops=False,
            schema="app",
            description="snap",
            source="live-database",
            snapshot_model=None,
            tags=None,
            exclude_tags=None,
            versions=None,
            exclude_versions=None,
            target_version=None,
        )
        assert opts.output == "/tmp/out.sql"
        assert opts.schema == "app"
        assert opts.description == "snap"
        assert opts.source == "live-database"

    def test_list_tables_joined_with_commas(self):
        """Per-kwarg ``tables=[...]`` is normalized to a comma-joined string."""
        from api._client_operations import _build_export_schema_options

        client = _make_client()
        opts = _build_export_schema_options(
            client,
            output=None,
            output_dir=None,
            split_by_type=False,
            tables=["users", "orders", "audit"],
            types=["TABLE", "VIEW"],
            unmanaged_only=False,
            managed_only=False,
            include_drops=False,
            schema=None,
            description=None,
            source="live-database",
            snapshot_model=None,
            tags=None,
            exclude_tags=None,
            versions=None,
            exclude_versions=None,
            target_version=None,
        )
        assert opts.tables == "users,orders,audit"
        assert opts.types == "TABLE,VIEW"

    def test_string_tables_passed_through_unchanged(self):
        """Already-string ``tables="a,b"`` is forwarded as-is."""
        from api._client_operations import _build_export_schema_options

        client = _make_client()
        opts = _build_export_schema_options(
            client,
            output=None,
            output_dir=None,
            split_by_type=False,
            tables="users,orders",
            types="TABLE",
            unmanaged_only=False,
            managed_only=False,
            include_drops=False,
            schema=None,
            description=None,
            source="live-database",
            snapshot_model=None,
            tags=None,
            exclude_tags=None,
            versions=None,
            exclude_versions=None,
            target_version=None,
        )
        assert opts.tables == "users,orders"
        assert opts.types == "TABLE"

    def test_pathlike_output_coerced_to_string(self):
        from api._client_operations import _build_export_schema_options

        client = _make_client()
        opts = _build_export_schema_options(
            client,
            output=Path("/tmp/out.sql"),
            output_dir=Path("/tmp/dir"),
            split_by_type=True,
            tables=None,
            types=None,
            unmanaged_only=False,
            managed_only=False,
            include_drops=False,
            schema=None,
            description=None,
            source="live-database",
            snapshot_model=Path("/tmp/snap.json"),
            tags=None,
            exclude_tags=None,
            versions=None,
            exclude_versions=None,
            target_version=None,
        )
        assert opts.output == "/tmp/out.sql"
        assert opts.output_dir == "/tmp/dir"
        assert opts.snapshot_model == "/tmp/snap.json"

    def test_additional_dirs_promoted_to_paths(self):
        from api._client_operations import _build_export_schema_options

        client = _make_client(additional_dirs=["/extra/a", "/extra/b"])
        opts = _build_export_schema_options(
            client,
            output=None,
            output_dir=None,
            split_by_type=False,
            tables=None,
            types=None,
            unmanaged_only=False,
            managed_only=False,
            include_drops=False,
            schema=None,
            description=None,
            source="live-database",
            snapshot_model=None,
            tags=None,
            exclude_tags=None,
            versions=None,
            exclude_versions=None,
            target_version=None,
        )
        assert opts.additional_scripts_dirs == [Path("/extra/a"), Path("/extra/b")]

    def test_no_additional_dirs_yields_none(self):
        """When the config has no ``directories`` extras, the option is ``None``
        — not an empty list — to mirror the legacy behavior."""
        from api._client_operations import _build_export_schema_options

        client = _make_client(additional_dirs=[])
        opts = _build_export_schema_options(
            client,
            output=None,
            output_dir=None,
            split_by_type=False,
            tables=None,
            types=None,
            unmanaged_only=False,
            managed_only=False,
            include_drops=False,
            schema=None,
            description=None,
            source="live-database",
            snapshot_model=None,
            tags=None,
            exclude_tags=None,
            versions=None,
            exclude_versions=None,
            target_version=None,
        )
        assert opts.additional_scripts_dirs is None


class TestExportSchemaOperation:
    def test_options_object_is_forwarded_unchanged(self):
        """A pre-built ``ExportSchemaOptions`` is sent to the impl as-is —
        no rebuild, no kwarg merge."""
        from api._client_operations import export_schema_operation
        from core.migration.commands.export_schema_command import ExportSchemaOptions

        client = _make_client()
        prebuilt = ExportSchemaOptions(output="/from/options.sql", schema="app")

        with patch("core.migration.commands.export_schema_command.export_schema") as impl:
            impl.return_value = True
            export_schema_operation(client, options=prebuilt)

        assert impl.call_args.kwargs["options"] is prebuilt

    def test_kwargs_path_used_when_options_omitted(self):
        from api._client_operations import export_schema_operation

        client = _make_client()
        with patch("core.migration.commands.export_schema_command.export_schema") as impl:
            impl.return_value = True
            export_schema_operation(client, output="/tmp/out.sql", schema="app")

        sent = impl.call_args.kwargs["options"]
        assert sent.output == "/tmp/out.sql"
        assert sent.schema == "app"

    def test_invalid_options_type_raises_typeerror(self):
        from api._client_operations import export_schema_operation

        client = _make_client()
        with pytest.raises(TypeError, match="ExportSchemaOptions"):
            export_schema_operation(client, options={"output": "/tmp/dict.sql"})

    def test_returns_completed_result_with_impl_success(self):
        from api._client_operations import export_schema_operation
        from api.events import EventType

        client = _make_client()
        with patch("core.migration.commands.export_schema_command.export_schema") as impl:
            impl.return_value = True
            result = export_schema_operation(client, output="/tmp/out.sql")

        assert result.success is True
        # ``result.complete()`` was called — end_time is set.
        assert result.end_time is not None
        client.events.emit.assert_any_call(
            EventType.EXPORT_COMPLETED,
            {"result": result, "operation": "export_schema"},
        )

    def test_returns_failed_result_when_impl_returns_false(self):
        from api._client_operations import export_schema_operation
        from api.events import EventType

        client = _make_client()
        with patch("core.migration.commands.export_schema_command.export_schema") as impl:
            impl.return_value = False
            result = export_schema_operation(client, output="/tmp/out.sql")

        assert result.success is False
        assert result.end_time is not None
        client.events.emit.assert_any_call(
            EventType.EXPORT_FAILED,
            {"result": result, "operation": "export_schema"},
        )
        assert all(
            call.args[0] is not EventType.EXPORT_COMPLETED
            for call in client.events.emit.call_args_list
        )
