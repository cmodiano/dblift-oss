"""BUG-02b regression: export-schema with 0 filtered objects is SUCCESS.

Before ADR-0013 PR-2, ``_generate_and_write`` wrote a valid empty export
file (``_write_empty_export``) and then returned ``False`` — the CLI
reported ``Command EXPORT-SCHEMA failed`` despite the file being on disk
and structurally correct. Empty-but-correct is a valid success outcome,
not a failure; "0 rows affected" is a real result of running a filter
against a schema that does not contain matching objects.

These tests pin the flipped contract: writing an empty export file is
success; ``run()`` returns ``True`` and the footer marks the command as
successful.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.migration.commands._schema_export_types import ExportExecutionState
from core.migration.commands.export_schema_command import SchemaExporter


def _make_exporter(output_path: Path) -> SchemaExporter:
    """Build a SchemaExporter with just enough state for _generate_and_write."""
    options = SimpleNamespace(
        output=str(output_path),
        output_dir=None,
        description=None,
        split_by_type=False,
    )
    exporter = SchemaExporter.__new__(SchemaExporter)
    exporter.log = MagicMock()
    exporter.options = options
    exporter.state = ExportExecutionState()
    exporter.state.dialect = "postgresql"
    # start_time is consumed by _log_command_footer — datetime-ish value needed.
    import datetime

    exporter.start_time = datetime.datetime.now()
    return exporter


@pytest.mark.unit
class TestGenerateAndWriteEmptyIsSuccess:
    def test_empty_filtered_list_returns_true_and_writes_file(self, tmp_path: Path):
        """BUG-02b: empty filtered list => empty file on disk + True (success)."""
        output = tmp_path / "empty-export.sql"
        exporter = _make_exporter(output)

        # Empty object list: the canonical trigger of BUG-02b.
        result = exporter._generate_and_write(filtered_objects=[], typed_lists={})

        assert result is True, "empty export is success; file was written"
        assert output.exists(), "empty export file must be on disk"
        content = output.read_text(encoding="utf-8")
        assert "No objects found" in content

    def test_empty_filtered_list_logs_at_warn_not_error(self, tmp_path: Path):
        """The empty path is an advisory outcome, not an error."""
        output = tmp_path / "empty-export.sql"
        exporter = _make_exporter(output)

        exporter._generate_and_write(filtered_objects=[], typed_lists={})

        # log.warn was called (advisory) but log.error was NOT.
        exporter.log.warn.assert_called()
        exporter.log.error.assert_not_called()
