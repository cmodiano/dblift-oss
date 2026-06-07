"""Unit tests for core.migration.commands.snapshot_command module.

Verifies that the core module is importable directly and that the
exported symbols are correct (AC#5: imports point to core/migration/commands/).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.migration.commands.snapshot_command import (
    SnapshotSource,
    _json_default,
    _log_command_footer,
    snapshot,
)
from core.utils.url_masking import mask_database_url


@pytest.mark.unit
class TestCoreSnapshotImports:
    """Verify core module exports the expected symbols."""

    def test_snapshot_callable(self):
        """snapshot is callable and importable from core."""
        assert callable(snapshot)

    def test_snapshot_source_enum_values(self):
        """SnapshotSource enum has expected values."""
        assert SnapshotSource.DATABASE_STORED == "database-stored"
        assert SnapshotSource.LIVE_DATABASE == "live-database"

    def test_helper_functions_callable(self):
        """Helper functions importable from core."""
        assert callable(_json_default)
        assert callable(_log_command_footer)


@pytest.mark.unit
class TestCoreSnapshotValidation:
    """Test snapshot validation without DB connections."""

    def test_snapshot_missing_output_returns_false(self):
        """snapshot returns (False, error_msg) when no output path given."""
        config = MagicMock()
        log = MagicMock()

        ok, err = snapshot(config=config, output=None, source="database-stored", log=log)

        assert ok is False
        assert err is not None
        log.error.assert_called()

    def test_snapshot_invalid_source_returns_false(self):
        """snapshot returns (False, error_msg) for invalid source."""
        config = MagicMock()
        log = MagicMock()

        ok, err = snapshot(config=config, output="/tmp/snap.json", source="invalid-source", log=log)

        assert ok is False
        assert err is not None
        log.error.assert_called()

    def test_snapshot_output_is_directory_returns_false(self, tmp_path):
        """snapshot returns (False, error_msg) when output path is a directory."""
        config = MagicMock()
        log = MagicMock()

        ok, err = snapshot(
            config=config,
            output=str(tmp_path),  # tmp_path is a directory, not a file
            source="database-stored",
            log=log,
        )

        assert ok is False
        assert err is not None
        log.error.assert_called()


@pytest.mark.unit
class TestCoreJsonDefault:
    """Test _json_default serializer."""

    def test_datetime_with_tz(self):
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _json_default(dt)
        assert "2024-01-01T12:00:00" in result

    def test_datetime_without_tz(self):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = _json_default(dt)
        assert isinstance(result, str)
        assert "2024-06-15" in result

    def test_enum_value(self):
        result = _json_default(SnapshotSource.DATABASE_STORED)
        assert result == "database-stored"

    def test_other_type_stringified(self):
        assert _json_default(42) == "42"


@pytest.mark.unit
class TestCoreMaskDatabaseUrl:
    """Test mask_database_url from core.utils.url_masking."""

    def test_masks_password_param(self):
        url = "postgresql+psycopg://localhost/db?password=secret"
        assert "secret" not in mask_database_url(url)
        assert "password=***" in mask_database_url(url)

    def test_masks_standard_jdbc_user_password_format(self):
        """Standard format //user:password@host (PostgreSQL, MySQL) must mask password."""
        url = "postgresql+psycopg://admin:secret@host:5432/db"
        masked = mask_database_url(url)
        assert "secret" not in masked
        assert "admin" in masked
        assert "***" in masked
        assert "//admin:***@host" in masked

    def test_masks_password_with_colon_in_standard_format(self):
        """Password containing : (e.g. connection string) must be fully masked."""
        url = "postgresql+psycopg://admin:pass:word@host:5432/db"
        masked = mask_database_url(url)
        assert "pass" not in masked
        assert "word" not in masked
        assert "admin" in masked
        assert "//admin:***@host" in masked

    def test_masks_password_with_slash_in_standard_format(self):
        """Password containing / must be fully masked."""
        url = "mysql+pymysql://user:p/ass@host:3306/db"
        masked = mask_database_url(url)
        assert "p/ass" not in masked
        assert "***" in masked
        assert "user" in masked

    def test_masks_cosmosdb_account_key(self):
        url = "AccountEndpoint=https://account.documents.azure.com/;AccountKey=abc123;"
        assert "abc123" not in mask_database_url(url)
        assert "AccountKey=***" in mask_database_url(url)

    def test_no_password_url_unchanged(self):
        url = "postgresql+psycopg://localhost/db?user=admin"
        assert mask_database_url(url) == url


@pytest.mark.unit
class TestCoreLogCommandFooter:
    """Test _log_command_footer from core snapshot_command module."""

    def test_success_message(self):
        import io
        import sys

        from core.logger.console import reset_stdout_console

        log_func = MagicMock()
        start_time = datetime.now() - timedelta(milliseconds=200)
        reset_stdout_console()
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _log_command_footer(log_func, success=True, start_time=start_time)
        finally:
            sys.stdout = old
            reset_stdout_console()
        assert "completed successfully" in buf.getvalue().lower()

    def test_failure_message(self):
        import io
        import sys

        from core.logger.console import reset_stdout_console

        log_func = MagicMock()
        start_time = datetime.now() - timedelta(seconds=1)
        reset_stdout_console()
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _log_command_footer(log_func, success=False, start_time=start_time)
        finally:
            sys.stdout = old
            reset_stdout_console()
        assert "failed" in buf.getvalue().lower()

    def test_with_log_set_command_completed(self):
        log_func = MagicMock()
        log = MagicMock()
        log.set_command_completed = MagicMock()
        start_time = datetime.now() - timedelta(milliseconds=50)
        _log_command_footer(log_func, success=True, start_time=start_time, log=log)
        log.set_command_completed.assert_called_once()
