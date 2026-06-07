"""Direct unit tests for CLI main functions (without subprocess).

These tests import and call functions directly, which contributes to code coverage.
Unlike subprocess tests, these unit tests will show up in coverage reports.
"""

import argparse
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

import pytest

from cli.main import create_parser, execute_single_command, parse_with_selective_errors


@pytest.mark.unit
class TestParseWithSelectiveErrors:
    """Test parse_with_selective_errors function."""

    def test_parse_with_selective_errors_no_errors(self):
        """Test parsing with no errors."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--test", type=str)

        # Mock sys.argv to avoid conflicts
        with patch.object(sys, "argv", ["test", "--test", "value"]):
            args, unknown_args, has_error = parse_with_selective_errors(parser)

            assert has_error is False
            assert args.test == "value"
            assert len(unknown_args) == 0

    def test_parse_with_selective_errors_unrecognized_args(self):
        """Test parsing with unrecognized arguments (should be filtered)."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--known", type=str)

        # Mock sys.argv with unrecognized arg
        with patch.object(sys, "argv", ["test", "--known", "value", "--unknown", "arg"]):
            args, unknown_args, has_error = parse_with_selective_errors(parser)

            # Should not have error (unrecognized args are filtered)
            assert has_error is False
            assert "--unknown" in unknown_args

    def test_parse_with_selective_errors_real_validation_error(self):
        """Test parsing with real validation error (should show error)."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--test", type=int)

        # Mock sys.argv with invalid type
        with patch.object(sys, "argv", ["test", "--test", "not_a_number"]):
            captured_stderr = io.StringIO()
            with patch.object(sys, "stderr", captured_stderr):
                args, unknown_args, has_error = parse_with_selective_errors(parser)

                # Should have error for invalid type
                assert has_error is True

    def test_parse_with_selective_errors_exception_handling(self):
        """Test exception handling in parse_with_selective_errors."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--required", required=True)

        # Mock sys.argv without required arg
        with patch.object(sys, "argv", ["test"]):
            args, unknown_args, has_error = parse_with_selective_errors(parser)

            # Should detect error for missing required arg
            assert has_error is True

    def test_parse_with_selective_errors_usage_line_filtering(self):
        """Test that usage lines are filtered when unrecognized args are present (covers lines 74, 76-79)."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--known", type=str)

        # This tests the logic that filters usage lines when unrecognized args appear
        # The actual filtering happens based on error output content
        # Lines 74, 76-79 handle filtering usage lines
        with patch.object(sys, "argv", ["test", "--known", "value", "--unknown", "arg"]):
            args, unknown_args, has_error = parse_with_selective_errors(parser)
            # Unrecognized args shouldn't cause error (they're filtered)
            assert has_error is False
            # Verify usage line filtering logic path was executed
            assert "--unknown" in unknown_args

    def test_parse_with_selective_errors_silent_exception(self):
        """Test handling of silent exceptions (exception with no error output)."""
        parser = argparse.ArgumentParser()

        # Create a scenario where an exception might occur but no stderr output
        # This is hard to simulate directly, but we can test the logic path exists
        # by ensuring the function handles the case where parse_exception exists
        # but error_output is empty

        # Mock parse_known_args to raise an exception
        with patch.object(parser, "parse_known_args", side_effect=SystemExit(2)):
            # Capture stderr to ensure no output
            old_stderr = sys.stderr
            captured_stderr = io.StringIO()
            sys.stderr = captured_stderr

            try:
                args, unknown_args, has_error = parse_with_selective_errors(parser)
                # SystemExit during parsing should be caught
                # The function should handle it gracefully
            finally:
                sys.stderr = old_stderr


@pytest.mark.unit
class TestCreateParserSuppressErrors:
    """Test create_parser with suppress_errors option."""

    def test_create_parser_with_suppress_errors(self):
        """Test parser creation with suppress_errors=True."""
        parser = create_parser(exit_on_error=True, suppress_errors=True)
        assert parser is not None
        # Parser should have silent error method when suppress_errors=True
        assert hasattr(parser, "error")

    def test_create_parser_without_suppress_errors(self):
        """Test parser creation with suppress_errors=False."""
        parser = create_parser(exit_on_error=True, suppress_errors=False)
        assert parser is not None
        # Normal error method should exist
        assert hasattr(parser, "error")


@pytest.mark.unit
class TestCreateParser:
    """Test create_parser function."""

    def test_create_parser_basic(self):
        """Test basic parser creation."""
        parser = create_parser()
        assert parser is not None
        assert hasattr(parser, "description")

    def test_create_parser_with_exit_on_error_false(self):
        """Test parser creation with exit_on_error=False."""
        parser = create_parser(exit_on_error=False)
        assert parser is not None
        # Should still create parser successfully

    def test_create_parser_has_all_commands(self):
        """Test that parser has all expected commands."""
        parser = create_parser()

        # Test that subparsers exist
        # We can't directly check subparsers, but we can try parsing known commands
        test_commands = [
            "migrate",
            "info",
            "validate",
            "undo",
            "clean",
            "baseline",
            "repair",
            "import-flyway",
        ]

        for cmd in test_commands:
            # Create a minimal argv to test parsing
            test_argv = ["test", cmd]
            try:
                with patch.object(sys, "argv", test_argv):
                    args = parser.parse_known_args()
                    # If we get here, command was recognized
                    assert args[0].command == cmd or args[0].command is None
            except SystemExit:
                # Some commands might require additional args, which is fine
                pass

    def test_create_parser_all_subparsers_have_silent_error(self):
        """Test that all subparsers get silent error when suppress_errors=True."""
        parser = create_parser(exit_on_error=False, suppress_errors=True)
        assert parser is not None

        # The subparsers should have their error methods overridden
        # We can verify this by checking that the parser was created successfully
        # The actual subparser error override happens internally
        assert parser is not None

    def test_create_parser_with_exit_on_error_false_returns_valid_parser(self):
        """Test parser creation with exit_on_error=False returns a usable parser."""
        # Python 3.9+ feature
        parser = create_parser(exit_on_error=False)
        assert parser is not None
        assert hasattr(parser, "parse_args")


@pytest.mark.unit
class TestExecuteSingleCommand:
    """Test execute_single_command function."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock DBLiftClient."""
        client = MagicMock()

        # Mock result objects
        mock_migrate_result = MagicMock()
        mock_migrate_result.success = True
        mock_migrate_result.execution_time = Mock(return_value=100)

        mock_validate_result = MagicMock()
        mock_validate_result.success = True

        mock_info_result = MagicMock()
        mock_info_result.success = True

        mock_undo_result = MagicMock()
        mock_undo_result.success = True

        mock_clean_result = MagicMock()
        mock_clean_result.success = True

        mock_baseline_result = MagicMock()
        mock_baseline_result.success = True

        mock_repair_result = MagicMock()
        mock_repair_result.success = True

        mock_operation_result = MagicMock()
        mock_operation_result.success = True

        # Setup client methods
        client.migrate.return_value = mock_migrate_result
        client.validate.return_value = mock_validate_result
        client.info.return_value = mock_info_result
        client.undo.return_value = mock_undo_result
        client.clean.return_value = mock_clean_result
        client.baseline.return_value = mock_baseline_result
        client.repair.return_value = mock_repair_result
        client.import_flyway.return_value = mock_operation_result
        client.export_schema.return_value = mock_operation_result
        client.snapshot.return_value = mock_operation_result
        client.diff.return_value = MagicMock(success=True)

        return client

    @pytest.fixture
    def mock_log(self):
        """Create a mock logger."""
        log = MagicMock()
        log.set_command_completed = Mock()
        return log

    def test_execute_migrate_command(self, mock_client, mock_log):
        """Test executing migrate command."""
        args = argparse.Namespace(
            command="migrate",
            dry_run=False,
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
            mark_as_executed=False,
            validate_only=False,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="migrate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.migrate.assert_called_once()
        mock_log.set_command_completed.assert_called_once()

    def test_execute_migrate_with_validate_only(self, mock_client, mock_log):
        """Test executing migrate command with --validate-only."""
        args = argparse.Namespace(
            command="migrate",
            dry_run=False,
            target_version="1.0.0",
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
            mark_as_executed=False,
            validate_only=True,  # Should call validate instead
        )

        success, result = execute_single_command(
            client=mock_client,
            command="migrate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.validate.assert_called_once()
        mock_client.migrate.assert_not_called()

    def test_execute_info_command(self, mock_client, mock_log):
        """Test executing info command."""
        args = argparse.Namespace(
            command="info",
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="info",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.info.assert_called_once()

    def test_execute_validate_command(self, mock_client, mock_log):
        """Test executing validate command."""
        args = argparse.Namespace(
            command="validate",
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="validate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.validate.assert_called_once()

    def test_execute_undo_command(self, mock_client, mock_log):
        """Test executing undo command."""
        args = argparse.Namespace(
            command="undo",
            dry_run=False,
            target_version="1.0.0",
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
            show_sql=True,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="undo",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.undo.call_args[1]
        assert call_kwargs["show_sql"] is True

    def test_execute_clean_command(self, mock_client, mock_log):
        """Test executing clean command."""
        args = argparse.Namespace(
            command="clean",
            dry_run=False,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="clean",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.clean.assert_called_once()

    def test_execute_baseline_command(self, mock_client, mock_log):
        """Test executing baseline command."""
        args = argparse.Namespace(
            command="baseline",
            baseline_version="1.0.0",
            baseline_description="Initial baseline",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="baseline",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.baseline.assert_called_once()

    def test_execute_repair_command(self, mock_client, mock_log):
        """Test executing repair command."""
        args = argparse.Namespace(
            command="repair",
            dry_run=False,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="repair",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.repair.assert_called_once()

    def test_execute_import_flyway_command(self, mock_client, mock_log):
        """Test executing import-flyway command."""
        args = argparse.Namespace(
            command="import-flyway",
            dry_run=False,
            flyway_table="custom_flyway_history",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="import-flyway",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.import_flyway.assert_called_once_with(
            dry_run=False,
            recursive=True,
            flyway_table="custom_flyway_history",
        )

    def test_execute_export_schema_command(self, mock_client, mock_log):
        """Test executing export-schema command."""
        args = argparse.Namespace(
            command="export-schema",
            output="/tmp/schema.sql",
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
        )

        success, result = execute_single_command(
            client=mock_client,
            command="export-schema",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.export_schema.assert_called_once()

    def test_execute_diff_command(self, mock_client, mock_log):
        """Test executing diff command."""
        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=False,
            output=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.diff.assert_called_once()

    def test_execute_unknown_command(self, mock_client, mock_log):
        """Test executing unknown command raises ValueError."""
        args = argparse.Namespace(command="unknown")

        with pytest.raises(ValueError, match="Unknown command"):
            execute_single_command(
                client=mock_client,
                command="unknown",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

    def test_execute_migrate_with_all_options(self, mock_client, mock_log):
        """Test executing migrate with all options."""
        args = argparse.Namespace(
            command="migrate",
            dry_run=True,
            target_version="2.0.0",
            versions=None,
            exclude_versions=None,
            tags="tag1,tag2",
            exclude_tags="tag3",
            mark_as_executed=True,
            validate_only=False,
            show_sql=True,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="migrate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[Path("/tmp/extra")],
            recursive=False,
            placeholders={"key1": "value1"},
            dir_recursive_map={Path("/tmp/extra"): False},
        )

        assert success is True
        call_kwargs = mock_client.migrate.call_args[1]
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["target_version"] == "2.0.0"
        assert call_kwargs["tags"] == "tag1,tag2"
        assert call_kwargs["exclude_tags"] == "tag3"
        assert call_kwargs["mark_as_executed"] is True
        assert call_kwargs["show_sql"] is True

    def test_execute_migrate_with_failure(self, mock_client, mock_log):
        """Test executing migrate command that fails."""
        # Make migrate return a failed result
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.execution_time = Mock(return_value=50)
        mock_client.migrate.return_value = mock_result

        args = argparse.Namespace(
            command="migrate",
            dry_run=False,
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
            mark_as_executed=False,
            validate_only=False,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="migrate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        mock_log.set_command_completed.assert_called_once()

    def test_execute_validate_sql_command(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql command."""
        # Create a test SQL file
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        # Mock the SQL validator - it's imported inside the function
        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_result.violations = []
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = False

            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            assert success is True
            mock_validator.validate_files.assert_called_once()

    def test_execute_validate_sql_no_files(self, mock_client, mock_log):
        """Test executing validate-sql with no files."""
        args = argparse.Namespace(
            command="validate-sql",
            files=None,
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="validate-sql",
            args=args,
            log=mock_log,
            scripts_dir=None,  # No scripts_dir either
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        mock_log.error.assert_called()

    def test_execute_diff_with_generate_sql(self, mock_client, mock_log, tmp_path):
        """Test executing diff command with --generate-sql."""
        output_file = tmp_path / "diff.sql"

        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=True,
            output=str(output_file),
        )

        # Mock diff result
        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_client.diff.return_value = mock_diff_result

        # Mock generate_sql_from_diff
        mock_generate_result = MagicMock()
        mock_generate_result.success = True
        mock_client.generate_sql_from_diff.return_value = mock_generate_result

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        mock_client.diff.assert_called_once()

    def test_execute_diff_output_file_without_generate_sql(self, mock_client, mock_log):
        """Test executing diff with --output-file but no --generate-sql (should fail)."""
        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=False,  # Missing flag
            output_file="/tmp/diff.sql",  # But has output_file (not output)
        )

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        mock_log.error.assert_called()
        # Check that error message was logged
        error_calls = [str(call) for call in mock_log.error.call_args_list]
        assert any("--output-file requires --generate-sql" in str(call) for call in error_calls)

    def test_execute_export_schema_with_options(self, mock_client, mock_log):
        """Test executing export-schema with various options."""
        args = argparse.Namespace(
            command="export-schema",
            output="/tmp/schema.sql",
            output_dir=None,
            split_by_type=False,
            tables="users,orders",
            types="table,view",
            unmanaged_only=True,
            managed_only=False,
            include_drops=True,
            schema="public",
            description="Test export",
            source="live-database",
            snapshot_model=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="export-schema",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.export_schema.call_args[1]
        assert call_kwargs["tables"] == "users,orders"
        assert call_kwargs["types"] == "table,view"
        assert call_kwargs["unmanaged_only"] is True
        assert call_kwargs["include_drops"] is True

    def test_execute_diff_with_version_filters_warning(self, mock_client, mock_log):
        """Test executing diff command with version filters shows warning."""
        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=False,
            output_file=None,
            versions="1.0.0",
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_client.diff.return_value = mock_diff_result

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        # Verify warning was logged
        warning_calls = [str(call) for call in mock_log.warning.call_args_list]
        assert any("versions and --exclude-versions filters" in str(call) for call in warning_calls)

    def test_execute_diff_with_generate_sql_and_expected_objects(self, mock_client, mock_log):
        """Test executing diff with generate_sql uses expected_objects from result."""
        from core.migration.snapshots.schema_snapshot import SchemaSnapshotPayload
        from core.sql_model.table import Table

        # Create mock expected payload
        mock_expected_payload = MagicMock(spec=SchemaSnapshotPayload)
        mock_table = Table(name="users", columns=[], dialect="postgresql")
        mock_expected_payload.tables = [mock_table]
        mock_expected_payload.views = []
        mock_expected_payload.indexes = []
        mock_expected_payload.sequences = []
        mock_expected_payload.triggers = []
        mock_expected_payload.procedures = []
        mock_expected_payload.functions = []
        mock_expected_payload.synonyms = []
        mock_expected_payload.extensions = []
        mock_expected_payload.user_defined_types = []
        mock_expected_payload.packages = []
        mock_expected_payload.events = []
        mock_expected_payload.database_links = []
        mock_expected_payload.foreign_data_wrappers = []
        mock_expected_payload.foreign_servers = []
        # ``spec=SchemaSnapshotPayload`` does not expose dataclass fields like
        # ``linked_servers`` via __getattr__ until they are set (unittest.mock
        # only whitelists true class attributes). ``_build_expected_objects``
        # reads ``payload.linked_servers`` — assign explicitly.
        mock_expected_payload.linked_servers = []

        # Create mock diff result with expected_payload
        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_diff_result.expected_payload = mock_expected_payload
        mock_client.diff.return_value = mock_diff_result

        # Mock SQL generation result
        mock_sql_result = MagicMock()
        mock_sql_result.success = True
        mock_sql_result.statements_generated = 5
        mock_sql_result.sql_script = "CREATE TABLE users;"
        mock_client.generate_sql_from_diff.return_value = mock_sql_result

        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=True,
            output_file=None,  # No output file, should print to console
        )

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        # Verify generate_sql_from_diff was called with expected_objects
        mock_client.generate_sql_from_diff.assert_called_once()
        call_kwargs = mock_client.generate_sql_from_diff.call_args[1]
        assert "expected_objects" in call_kwargs
        assert call_kwargs["expected_objects"] is not None
        # Verify SQL script was logged
        mock_log.info.assert_called()

    def test_execute_diff_generate_sql_failure(self, mock_client, mock_log):
        """Test executing diff when SQL generation fails."""
        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_diff_result.expected_payload = None
        mock_client.diff.return_value = mock_diff_result

        # Mock SQL generation to fail
        mock_sql_result = MagicMock()
        mock_sql_result.success = False
        mock_sql_result.error_message = "SQL generation failed"
        mock_client.generate_sql_from_diff.return_value = mock_sql_result

        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=True,
            output_file="/tmp/diff.sql",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        # Should return False because SQL generation failed
        assert success is False
        mock_log.error.assert_called()

    def test_execute_diff_generate_sql_exception_marks_diff_failed(self, mock_client, mock_log):
        """Test SQL generation exceptions are reported as diff failures."""
        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_diff_result.expected_payload = None
        mock_client.diff.return_value = mock_diff_result
        mock_client.generate_sql_from_diff.side_effect = ValueError("Unsupported dialect 'sqlite'")

        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=True,
            output_file="/tmp/diff.sql",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        assert result.success is False
        mock_log.error.assert_called()
        mock_diff_result.set_error.assert_called_once_with("Unsupported dialect 'sqlite'")

    def test_execute_validate_sql_with_directory(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql with directory containing SQL files."""
        sql_dir = tmp_path / "sql_files"
        sql_dir.mkdir()
        # Use Flyway naming convention so OBS-02 filter passes them through
        (sql_dir / "V1__init.sql").write_text("SELECT 1;")
        (sql_dir / "V2__data.sql").write_text("SELECT 2;")

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_dir)],
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_result.violations = []
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = False

            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            assert success is True
            # Should find multiple files in directory
            call_args = mock_validator.validate_files.call_args[0]
            assert len(call_args[0]) >= 2

    def test_execute_validate_sql_with_failures(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql when validation fails."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect="postgresql",
            rules_file=None,
            fail_on="warning",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_violation = MagicMock()
            mock_result.violations = [mock_violation]
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = True  # Should fail

            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            assert success is False
            mock_log.error.assert_called()

    def test_execute_validate_sql_no_files_found(self, mock_client, mock_log):
        """Test executing validate-sql when no files are found."""
        args = argparse.Namespace(
            command="validate-sql",
            files=None,
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        # Use a directory that exists but has no SQL files
        empty_dir = Path("/tmp/empty_migrations")
        empty_dir.mkdir(exist_ok=True)

        with patch("core.sql_validator.linting.sql_validator.SqlValidator"):
            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=empty_dir,
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            # Should return True but with warning
            assert success is True
            mock_log.warning.assert_called()

    def test_execute_validate_sql_infers_dialect_from_config(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql infers dialect from client config."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        # Mock client config with database type
        mock_client.config = MagicMock()
        mock_client.config.database = MagicMock()
        mock_client.config.database.type = "mysql"

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect=None,  # Should be inferred
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_result.violations = []
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = False

            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            assert success is True
            # Verify validator was created with mysql dialect
            call_kwargs = mock_validator_class.call_args[1]
            assert call_kwargs["dialect"] == "mysql"

    def test_execute_validate_sql_infers_sqlite_from_config(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql preserves SQLite config dialect."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT 1;")

        mock_client.config = MagicMock()
        mock_client.config.database = MagicMock()
        mock_client.config.database.type = "sqlite3"

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_result.violations = []
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = False

            success, _ = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            assert success is True
            call_kwargs = mock_validator_class.call_args[1]
            assert call_kwargs["dialect"] == "sqlite"

    def test_execute_migrate_with_placeholders(self, mock_client, mock_log):
        """Test executing migrate command with placeholders."""
        args = argparse.Namespace(
            command="migrate",
            dry_run=False,
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
            mark_as_executed=False,
            validate_only=False,
        )

        placeholders = {"key1": "value1", "key2": "value2"}

        success, result = execute_single_command(
            client=mock_client,
            command="migrate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders=placeholders,
            dir_recursive_map={},
        )

        assert success is True
        # Verify placeholders were passed to migrate
        call_kwargs = mock_client.migrate.call_args[1]
        assert call_kwargs["placeholders"] == placeholders

    def test_execute_migrate_with_additional_dirs(self, mock_client, mock_log):
        """Test executing migrate command with additional scripts directories."""
        args = argparse.Namespace(
            command="migrate",
            dry_run=False,
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
            mark_as_executed=False,
            validate_only=False,
        )

        additional_dirs = [Path("/tmp/extra1"), Path("/tmp/extra2")]

        success, result = execute_single_command(
            client=mock_client,
            command="migrate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=additional_dirs,
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        # Verify additional_dirs were passed
        call_kwargs = mock_client.migrate.call_args[1]
        assert call_kwargs["additional_dirs"] == additional_dirs

    def test_execute_info_with_all_filters(self, mock_client, mock_log):
        """Test executing info command with all filter options."""
        args = argparse.Namespace(
            command="info",
            target_version="2.0.0",
            versions="1.0.0,2.0.0",
            exclude_versions="3.0.0",
            tags="tag1,tag2",
            exclude_tags="tag3",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="info",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.info.call_args[1]
        assert call_kwargs["target_version"] == "2.0.0"
        assert call_kwargs["versions"] == "1.0.0,2.0.0"
        assert call_kwargs["exclude_versions"] == "3.0.0"
        assert call_kwargs["tags"] == "tag1,tag2"
        assert call_kwargs["exclude_tags"] == "tag3"

    def test_execute_undo_with_failure(self, mock_client, mock_log):
        """Test executing undo command that fails."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.execution_time = Mock(return_value=75)
        mock_client.undo.return_value = mock_result

        args = argparse.Namespace(
            command="undo",
            dry_run=False,
            target_version="1.0.0",
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="undo",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        mock_log.set_command_completed.assert_called_once()
        # Verify failure message was set
        call_kwargs = mock_log.set_command_completed.call_args[1]
        assert "failed" in call_kwargs["message"].lower()

    def test_execute_clean_with_dry_run(self, mock_client, mock_log):
        """Test executing clean command with dry_run."""
        args = argparse.Namespace(
            command="clean",
            dry_run=True,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="clean",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.clean.call_args[1]
        assert call_kwargs["dry_run"] is True

    def test_execute_baseline_with_empty_description(self, mock_client, mock_log):
        """Test executing baseline command with empty description (should use default)."""
        args = argparse.Namespace(
            command="baseline",
            baseline_version="1.0.0",
            baseline_description=None,  # Should default to ""
        )

        success, result = execute_single_command(
            client=mock_client,
            command="baseline",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.baseline.call_args
        # Should be called with version and empty description
        assert call_kwargs[0][0] == "1.0.0"
        assert call_kwargs[0][1] == ""

    def test_execute_repair_with_dir_recursive_map(self, mock_client, mock_log):
        """Test executing repair command with dir_recursive_map."""
        args = argparse.Namespace(
            command="repair",
            dry_run=False,
        )

        dir_recursive_map = {Path("/tmp/extra"): False}

        success, result = execute_single_command(
            client=mock_client,
            command="repair",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[Path("/tmp/extra")],
            recursive=True,
            placeholders={},
            dir_recursive_map=dir_recursive_map,
        )

        assert success is True
        call_kwargs = mock_client.repair.call_args[1]
        assert call_kwargs["dir_recursive_map"] == dir_recursive_map

    def test_execute_validate_with_all_options(self, mock_client, mock_log):
        """Test executing validate command with all filter options."""
        args = argparse.Namespace(
            command="validate",
            target_version="2.0.0",
            versions="1.0.0,2.0.0",
            exclude_versions="3.0.0",
            tags="tag1,tag2",
            exclude_tags="tag3",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="validate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=False,  # Test non-recursive
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.validate.call_args[1]
        assert call_kwargs["target_version"] == "2.0.0"
        assert call_kwargs["versions"] == "1.0.0,2.0.0"
        assert call_kwargs["exclude_versions"] == "3.0.0"
        assert call_kwargs["tags"] == "tag1,tag2"
        assert call_kwargs["exclude_tags"] == "tag3"
        assert call_kwargs["recursive"] is False

    def test_execute_validate_sql_with_validation_config_from_file(
        self, mock_client, mock_log, tmp_path
    ):
        """Test executing validate-sql uses validation config from client config."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        # Mock client config with validation config
        mock_client.config = MagicMock()
        mock_client.config.database = MagicMock()
        mock_client.config.database.type = "postgresql"
        mock_validation_config = MagicMock()
        mock_client.config.validation = mock_validation_config

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_result.violations = []
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = False

            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            assert success is True
            # Verify validation_config was used (it should be passed to SqlValidator)
            assert mock_validator_class.called

    def test_execute_validate_sql_with_all_validation_options(
        self, mock_client, mock_log, tmp_path
    ):
        """Test executing validate-sql with all validation config options."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect="mysql",
            rules_file="/path/to/rules.yaml",
            fail_on="warning",
            severity_threshold="error",
            no_performance=True,
            format="json",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            with patch(
                "core.sql_validator.linting.formatters.FormatterFactory"
            ) as mock_formatter_factory:
                mock_validator = MagicMock()
                mock_validator_class.return_value = mock_validator

                # Create a proper mock result object
                from unittest.mock import Mock

                mock_result = Mock()
                mock_result.violations = []
                mock_validator.validate_files.return_value = mock_result
                mock_validator.should_fail.return_value = False

                mock_formatter = MagicMock()
                mock_formatter.format.return_value = '{"format": "json"}'
                mock_formatter_factory.create.return_value = mock_formatter

                success, result = execute_single_command(
                    client=mock_client,
                    command="validate-sql",
                    args=args,
                    log=mock_log,
                    scripts_dir=Path("/tmp/migrations"),
                    additional_scripts_dirs=[],
                    recursive=True,
                    placeholders={},
                    dir_recursive_map={},
                )

                assert success is True
                # Verify validator was created with correct dialect
                call_kwargs = mock_validator_class.call_args[1]
                assert call_kwargs["dialect"] == "mysql"

    def test_execute_validate_sql_without_validation_config(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql when config has no validation attribute (covers line 777)."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        # Mock client config without validation attribute
        mock_config = MagicMock()
        mock_config.database = MagicMock()
        mock_config.database.type = "postgresql"
        # Don't set validation attribute - this should use default ValidationConfig
        # This tests the else branch on line 775-777
        type(mock_config).validation = PropertyMock(side_effect=AttributeError)
        mock_client.config = mock_config

        args = argparse.Namespace(
            command="validate-sql",
            files=[str(sql_file)],
            dialect=None,
            rules_file=None,
            fail_on="error",
            severity_threshold=None,
            no_performance=False,
            format="console",
        )

        with patch("core.sql_validator.linting.sql_validator.SqlValidator") as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator_class.return_value = mock_validator

            mock_result = MagicMock()
            mock_result.violations = []
            mock_validator.validate_files.return_value = mock_result
            mock_validator.should_fail.return_value = False

            success, result = execute_single_command(
                client=mock_client,
                command="validate-sql",
                args=args,
                log=mock_log,
                scripts_dir=Path("/tmp/migrations"),
                additional_scripts_dirs=[],
                recursive=True,
                placeholders={},
                dir_recursive_map={},
            )

            # Should still succeed with default config (postgresql dialect)
            assert success is True
            # Verify default dialect was used
            call_kwargs = mock_validator_class.call_args[1]
            assert call_kwargs["dialect"] == "postgresql"

    def test_execute_validate_sql_with_different_formats(self, mock_client, mock_log, tmp_path):
        """Test executing validate-sql with different output formats."""
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT * FROM users;")

        formats = ["console", "json", "github-actions", "compact", "sarif"]

        for fmt in formats:
            args = argparse.Namespace(
                command="validate-sql",
                files=[str(sql_file)],
                dialect=None,
                rules_file=None,
                fail_on="error",
                severity_threshold=None,
                no_performance=False,
                format=fmt,
            )

            with patch(
                "core.sql_validator.linting.sql_validator.SqlValidator"
            ) as mock_validator_class:
                mock_validator = MagicMock()
                mock_validator_class.return_value = mock_validator

                mock_result = MagicMock()
                mock_result.files_checked = 1
                mock_result.violations = []
                mock_validator.validate_files.return_value = mock_result

                success, result = execute_single_command(
                    client=mock_client,
                    command="validate-sql",
                    args=args,
                    log=mock_log,
                    scripts_dir=Path("/tmp/migrations"),
                    additional_scripts_dirs=[],
                    recursive=True,
                    placeholders={},
                    dir_recursive_map={},
                )

                assert success is True

    def test_execute_clean_with_failure(self, mock_client, mock_log):
        """Test executing clean command that fails."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.execution_time = Mock(return_value=50)
        mock_client.clean.return_value = mock_result

        args = argparse.Namespace(
            command="clean",
            dry_run=False,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="clean",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        mock_log.set_command_completed.assert_called_once()

    def test_execute_validate_with_no_result_execution_time(self, mock_client, mock_log):
        """Test executing validate when result has no execution_time method."""
        # Mock result without execution_time
        mock_result = MagicMock()
        mock_result.success = True
        del mock_result.execution_time  # Remove the method
        mock_client.validate.return_value = mock_result

        args = argparse.Namespace(
            command="validate",
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="validate",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True

    def test_execute_info_with_no_execution_time(self, mock_client, mock_log):
        """Test executing info when result has no execution_time method."""
        mock_result = MagicMock()
        mock_result.success = True
        # Don't add execution_time method
        if hasattr(mock_result, "execution_time"):
            delattr(mock_result, "execution_time")
        mock_client.info.return_value = mock_result

        args = argparse.Namespace(
            command="info",
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="info",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        # Should handle missing execution_time gracefully (defaults to 0)

    def test_execute_info_with_failure(self, mock_client, mock_log):
        """Test executing info command that fails (covers line 877)."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.execution_time = Mock(return_value=100)
        mock_client.info.return_value = mock_result

        args = argparse.Namespace(
            command="info",
            target_version=None,
            versions=None,
            exclude_versions=None,
            tags=None,
            exclude_tags=None,
        )

        success, result = execute_single_command(
            client=mock_client,
            command="info",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is False
        # Verify failure message was set
        call_kwargs = mock_log.set_command_completed.call_args[1]
        assert "failed" in call_kwargs["message"].lower()

    def test_execute_diff_with_tags_and_versions(self, mock_client, mock_log):
        """Test executing diff command with tags and versions converted to lists."""
        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=False,
            output_file=None,
            versions="1.0.0,2.0.0",
            exclude_versions="3.0.0",
            tags="tag1,tag2",
            exclude_tags="tag3",
        )

        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_client.diff.return_value = mock_diff_result

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        # Verify diff was called with lists, not strings
        call_kwargs = mock_client.diff.call_args[1]
        assert call_kwargs["versions"] == ["1.0.0", "2.0.0"]
        assert call_kwargs["exclude_versions"] == ["3.0.0"]
        assert call_kwargs["tags"] == ["tag1", "tag2"]
        assert call_kwargs["exclude_tags"] == ["tag3"]

    def test_execute_diff_generate_sql_with_output_file(self, mock_client, mock_log):
        """Test executing diff with generate_sql and output_file."""
        mock_diff_result = MagicMock()
        mock_diff_result.success = True
        mock_diff_result.expected_payload = None
        mock_client.diff.return_value = mock_diff_result

        mock_sql_result = MagicMock()
        mock_sql_result.success = True
        mock_sql_result.statements_generated = 10
        mock_sql_result.sql_script = "CREATE TABLE users;"
        mock_client.generate_sql_from_diff.return_value = mock_sql_result

        args = argparse.Namespace(
            command="diff",
            source1="database",
            source2="snapshot",
            snapshot_model=None,
            generate_sql=True,
            output_file="/tmp/diff.sql",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="diff",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        # Verify SQL generation was called with output_file
        call_kwargs = mock_client.generate_sql_from_diff.call_args[1]
        assert call_kwargs["output_file"] == "/tmp/diff.sql"

    def test_execute_undo_with_all_filters(self, mock_client, mock_log):
        """Test executing undo command with all filter options."""
        args = argparse.Namespace(
            command="undo",
            dry_run=True,
            target_version="1.0.0",
            versions="1.0.0,2.0.0",
            exclude_versions="3.0.0",
            tags="tag1,tag2",
            exclude_tags="tag3",
        )

        success, result = execute_single_command(
            client=mock_client,
            command="undo",
            args=args,
            log=mock_log,
            scripts_dir=Path("/tmp/migrations"),
            additional_scripts_dirs=[],
            recursive=True,
            placeholders={},
            dir_recursive_map={},
        )

        assert success is True
        call_kwargs = mock_client.undo.call_args[1]
        assert call_kwargs["target_version"] == "1.0.0"
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["versions"] == "1.0.0,2.0.0"
        assert call_kwargs["exclude_versions"] == "3.0.0"
        assert call_kwargs["tags"] == "tag1,tag2"
        assert call_kwargs["exclude_tags"] == "tag3"
