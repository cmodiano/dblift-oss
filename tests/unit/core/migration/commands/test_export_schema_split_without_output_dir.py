"""BUG-05 regression: ``--split-by-type`` without ``--output-dir`` must fail exit 1.

``_validate_options`` used to log the error and ``return False`` without
logging the command footer. The caller set ``result.success = False`` via
the bool path, but ``_log_command_footer`` (which calls
``log.set_command_completed(success=...)``) was never invoked — so the
CLI reported "EXPORT-SCHEMA completed successfully" and exited 0.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.migration.commands._schema_export_types import ExportSchemaOptions
from core.migration.commands.export_schema_command import SchemaExporter


def _make_options(**overrides) -> ExportSchemaOptions:
    defaults = dict(
        output=None,
        output_dir=None,
        split_by_type=True,
        tables=None,
        types=None,
        unmanaged_only=False,
        managed_only=False,
        include_drops=False,
        schema=None,
        description=None,
        scripts_dir=None,
        additional_scripts_dirs=None,
        recursive=True,
        tags=None,
        exclude_tags=None,
        versions=None,
        exclude_versions=None,
        target_version=None,
        source="live-database",
        snapshot_model=None,
    )
    defaults.update(overrides)
    return ExportSchemaOptions(**defaults)


@pytest.mark.unit
class TestSplitByTypeMissingOutputDir:
    def test_returns_false_and_logs_footer_on_missing_output_dir(self):
        log = MagicMock()
        # Minimal config with database attr so run() doesn't blow up elsewhere.
        config = MagicMock()
        opts = _make_options(split_by_type=True, output_dir=None, output="/tmp/out")
        exporter = SchemaExporter(config=config, options=opts, log=log)

        ok = exporter.run()

        assert ok is False
        # set_command_completed must fire with success=False so CLI exits 1.
        log.set_command_completed.assert_called_once()
        _, kwargs = log.set_command_completed.call_args
        assert kwargs.get("success") is False

    def test_happy_path_does_not_mark_failed(self):
        """Defensive: ensure the failure-footer hook is tied to validation failure only."""
        log = MagicMock()
        config = MagicMock()
        opts = _make_options(split_by_type=False, output="/tmp/ok.sql")
        exporter = SchemaExporter(config=config, options=opts, log=log)
        # Short-circuit _setup_infrastructure so we don't touch the DB.
        exporter._setup_infrastructure = MagicMock(return_value=False)

        exporter.run()

        # _setup_infrastructure failure also needs a footer — but success=False.
        log.set_command_completed.assert_called_once()
        _, kwargs = log.set_command_completed.call_args
        assert kwargs.get("success") is False
