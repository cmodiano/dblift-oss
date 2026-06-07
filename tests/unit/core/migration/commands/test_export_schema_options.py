"""Unit tests for ExportSchemaOptions dataclass."""

from dataclasses import fields, is_dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.migration.commands.export_schema_command import (
    ExportSchemaOptions,
    export_schema,
)


@pytest.mark.unit
class TestExportSchemaOptionsStructure:
    """Tests for ExportSchemaOptions dataclass structure (AC#7 T5.1)."""

    def test_export_schema_options_is_dataclass(self):
        """ExportSchemaOptions is a Python dataclass."""
        assert is_dataclass(ExportSchemaOptions)
        assert len(fields(ExportSchemaOptions)) >= 20

    def test_export_schema_options_default_values(self):
        """Default values are correct."""
        opts = ExportSchemaOptions()
        assert opts.source == "live-database"
        assert opts.recursive is True
        assert opts.split_by_type is False
        assert opts.unmanaged_only is False
        assert opts.managed_only is False
        assert opts.include_drops is False
        assert opts.output is None
        assert opts.output_dir is None
        assert opts.schema is None
        assert opts.tables is None
        assert opts.types is None
        assert opts.tags is None
        assert opts.exclude_tags is None
        assert opts.versions is None
        assert opts.exclude_versions is None
        assert opts.target_version is None
        assert opts.description is None
        assert opts.snapshot_model is None
        assert opts.scripts_dir is None
        assert opts.additional_scripts_dirs is None
        assert opts.dir_recursive_map is None

    def test_export_schema_options_all_fields(self):
        """All fields can be set."""
        opts = ExportSchemaOptions(
            output="out.sql",
            output_dir="/tmp",
            split_by_type=True,
            include_drops=True,
            description="test",
            source="file-model",
            snapshot_model="snap.json",
            tables="users,orders",
            types="table,view",
            schema="public",
            unmanaged_only=True,
            managed_only=False,
            tags="v1",
            exclude_tags="v2",
            versions="1.0",
            exclude_versions="2.0",
            target_version="3.0",
            scripts_dir=Path("/migrations"),
            additional_scripts_dirs=[Path("/extra")],
            dir_recursive_map={Path("/migrations"): True},
            recursive=False,
        )
        assert opts.output == "out.sql"
        assert opts.output_dir == "/tmp"
        assert opts.split_by_type is True
        assert opts.include_drops is True
        assert opts.description == "test"
        assert opts.source == "file-model"
        assert opts.snapshot_model == "snap.json"
        assert opts.tables == "users,orders"
        assert opts.types == "table,view"
        assert opts.schema == "public"
        assert opts.unmanaged_only is True
        assert opts.managed_only is False
        assert opts.tags == "v1"
        assert opts.exclude_tags == "v2"
        assert opts.versions == "1.0"
        assert opts.exclude_versions == "2.0"
        assert opts.target_version == "3.0"
        assert opts.scripts_dir == Path("/migrations")
        assert opts.additional_scripts_dirs == [Path("/extra")]
        assert opts.dir_recursive_map == {Path("/migrations"): True}
        assert opts.recursive is False

    def test_export_schema_options_importable(self):
        """ExportSchemaOptions is importable from core.migration.commands."""
        from core.migration.commands.export_schema_command import ExportSchemaOptions as ESO

        assert ESO is ExportSchemaOptions


@pytest.mark.unit
class TestExportSchemaOptionsBehavior:
    """Tests for export_schema behavior via ExportSchemaOptions (AC#7 T5.2)."""

    def test_export_schema_callable_with_options(self):
        """export_schema accepts (config, options) as positional params."""
        config = MagicMock()
        config.database.schema = "public"
        config.database.type = "postgresql"
        # Missing output → validation error → False (confirms function is callable)
        opts = ExportSchemaOptions(output=None, output_dir=None, source="live-database")
        result = export_schema(config, opts)
        assert result is False

    def test_export_schema_invalid_source_returns_false_via_options(self):
        """Invalid source in options returns False."""
        config = MagicMock()
        config.database.schema = "public"
        config.database.type = "postgresql"
        opts = ExportSchemaOptions(source="bad-source", output="out.sql")
        assert export_schema(config, opts) is False

    def test_export_schema_missing_output_returns_false_via_options(self):
        """output=None and output_dir=None returns False."""
        config = MagicMock()
        config.database.schema = "public"
        config.database.type = "postgresql"
        opts = ExportSchemaOptions(output=None, output_dir=None)
        assert export_schema(config, opts) is False

    def test_export_schema_unmanaged_and_managed_conflict_returns_false(self):
        """unmanaged_only + managed_only returns False."""
        config = MagicMock()
        config.database.schema = "public"
        config.database.type = "postgresql"
        opts = ExportSchemaOptions(
            output="out.sql",
            unmanaged_only=True,
            managed_only=True,
        )
        assert export_schema(config, opts) is False

    def test_export_schema_split_by_type_without_output_dir_returns_false(self):
        """split_by_type=True without output_dir returns False."""
        config = MagicMock()
        config.database.schema = "public"
        config.database.type = "postgresql"
        opts = ExportSchemaOptions(
            output="out.sql",
            split_by_type=True,
        )
        assert export_schema(config, opts) is False

    def test_export_schema_options_output_and_output_dir_conflict(self):
        """output + output_dir returns False."""
        config = MagicMock()
        config.database.schema = "public"
        config.database.type = "postgresql"
        opts = ExportSchemaOptions(output="out.sql", output_dir="/tmp")
        assert export_schema(config, opts) is False
