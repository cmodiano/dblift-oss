"""Extended tests for core.logger.results to improve coverage.

This module tests additional scenarios for the results module, focusing on
uncovered areas like CleanResult helper methods, DiffResult set_schema_diff,
unmanaged objects, and various result types.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from core.logger.results import (
    CleanResult,
    GenerateUndoScriptResult,
    MigrateResult,
    MigrationInfo,
    OperationResult,
    UndoResult,
)


@pytest.mark.unit
class TestCleanResultExtended:
    """Extended tests for CleanResult."""

    def test_add_view_dropped(self):
        """Test add_view_dropped helper method."""
        result = CleanResult()
        result.add_view_dropped("view1")
        result.add_view_dropped("view2")

        assert len(result.views_dropped) == 2
        assert "view1" in result.views_dropped
        assert "view2" in result.views_dropped

    def test_add_function_dropped(self):
        """Test add_function_dropped helper method."""
        result = CleanResult()
        result.add_function_dropped("func1")
        result.add_function_dropped("func2")

        assert len(result.functions_dropped) == 2
        assert "func1" in result.functions_dropped
        assert "func2" in result.functions_dropped

    def test_add_procedure_dropped(self):
        """Test add_procedure_dropped helper method."""
        result = CleanResult()
        result.add_procedure_dropped("proc1")
        result.add_procedure_dropped("proc2")

        assert len(result.procedures_dropped) == 2
        assert "proc1" in result.procedures_dropped
        assert "proc2" in result.procedures_dropped

    def test_add_sequence_dropped(self):
        """Test add_sequence_dropped helper method."""
        result = CleanResult()
        result.add_sequence_dropped("seq1")
        result.add_sequence_dropped("seq2")

        assert len(result.sequences_dropped) == 2
        assert "seq1" in result.sequences_dropped
        assert "seq2" in result.sequences_dropped

    def test_add_trigger_dropped(self):
        """Test add_trigger_dropped helper method."""
        result = CleanResult()
        result.add_trigger_dropped("trg1")
        result.add_trigger_dropped("trg2")

        assert len(result.triggers_dropped) == 2
        assert "trg1" in result.triggers_dropped
        assert "trg2" in result.triggers_dropped

    def test_add_cleaned_object_empty_name(self):
        """Test add_cleaned_object with empty name."""
        result = CleanResult()
        result.add_cleaned_object("table", "")

        assert len(result.tables_dropped) == 0

    def test_add_cleaned_object_empty_type(self):
        """Test add_cleaned_object with empty type."""
        result = CleanResult()
        result.add_cleaned_object("", "table1")

        assert len(result.tables_dropped) == 0

    def test_add_cleaned_object_with_schema(self):
        """Test add_cleaned_object with schema."""
        result = CleanResult()
        result.add_cleaned_object("table", "table1", schema="test_schema")

        assert "table1" in result.tables_dropped
        assert result.schema_name == "test_schema"
        details = result.get_object_details("table", "table1")
        assert details["schema"] == "test_schema"

    def test_add_cleaned_object_with_details(self):
        """Test add_cleaned_object with details."""
        result = CleanResult()
        result.add_cleaned_object("table", "table1", details={"key": "value", "number": 123})

        details = result.get_object_details("table", "table1")
        assert details["key"] == "value"
        assert details["number"] == "123"  # Converted to string

    def test_add_cleaned_object_normalizes_name(self):
        """Test add_cleaned_object normalizes name."""
        result = CleanResult()
        result.add_cleaned_object("table", '  "table1"  ')

        assert "table1" in result.tables_dropped

    def test_get_object_details_not_found(self):
        """Test get_object_details for non-existent object."""
        result = CleanResult()
        details = result.get_object_details("table", "nonexistent")

        assert details == {}

    def test_get_object_details_normalized_type(self):
        """Test get_object_details normalizes type."""
        result = CleanResult()
        result.add_cleaned_object("TABLE", "table1", schema="test")

        details = result.get_object_details("  TABLE  ", "table1")
        assert details["schema"] == "test"


@pytest.mark.unit
class TestUndoResult:
    """Tests for UndoResult."""

    def test_init(self):
        """Test UndoResult initialization."""
        result = UndoResult()

        assert result.success is True
        assert result.target_version == ""
        assert result.target_schema == ""
        assert result.schema_name == ""
        assert result.current_schema_version is None
        assert result.undone_migrations == []
        assert result.undone_count == 0

    def test_add_undone_migration(self):
        """Test add_undone_migration method."""
        result = UndoResult()
        migration = MigrationInfo("V1__Test.sql", version="1.0.0")

        result.add_undone_migration(migration)

        assert len(result.undone_migrations) == 1
        assert result.undone_count == 1

    def test_add_undone_migration_multiple(self):
        """Test add_undone_migration with multiple migrations."""
        result = UndoResult()
        migration1 = MigrationInfo("V1__Test.sql", version="1.0.0")
        migration2 = MigrationInfo("V2__Test.sql", version="2.0.0")

        result.add_undone_migration(migration1)
        result.add_undone_migration(migration2)

        assert len(result.undone_migrations) == 2
        assert result.undone_count == 2

    def test_migrations_property(self):
        """Test migrations property."""
        result = UndoResult()
        migration = MigrationInfo("V1__Test.sql", version="1.0.0")
        result.add_undone_migration(migration)

        assert result.migrations == result.undone_migrations


@pytest.mark.unit
class TestGenerateUndoScriptResult:
    """Tests for GenerateUndoScriptResult."""

    def test_init(self):
        """Test GenerateUndoScriptResult initialization."""
        result = GenerateUndoScriptResult()

        assert result.success is True
        assert result.migration_path is None
        assert result.undo_script_path is None
        assert result.overwritten is False
        assert result.statements_generated == 0
        assert result.requires_manual_review is False

    def test_add_warning_with_manual_review(self):
        """Test add_warning sets requires_manual_review."""
        result = GenerateUndoScriptResult()
        result.add_warning("This requires manual review")

        assert result.requires_manual_review is True

    def test_add_warning_with_warning_keyword(self):
        """Test add_warning with 'warning' keyword."""
        result = GenerateUndoScriptResult()
        result.add_warning("Warning: potential issue")

        assert result.requires_manual_review is True

    def test_add_warning_without_keywords(self):
        """Test add_warning without manual review keywords."""
        result = GenerateUndoScriptResult()
        result.add_warning("Simple message")

        assert result.requires_manual_review is False


@pytest.mark.unit
class TestMigrateResultExtended:
    """Extended tests for MigrateResult."""

    def test_add_migration_with_success_status(self):
        """Test add_migration with 'Success' status (backward compatibility)."""
        result = MigrateResult()
        migration = MigrationInfo("test.sql", status="Success")

        result.add_migration(migration)

        assert result.success is True
        assert len(result.migrations) == 1

    def test_is_successful_with_success_status(self):
        """Test is_successful with 'Success' status."""
        result = MigrateResult()
        migration = MigrationInfo("test.sql", status="Success")
        result.add_migration(migration)

        assert result.is_successful() is True

    def test_migrations_applied_with_success_status(self):
        """Test migrations_applied with 'Success' status."""
        result = MigrateResult()
        migration = MigrationInfo("V1__Test.sql", version="1.0.0", status="Success")
        result.add_migration(migration)

        applied = result.migrations_applied
        assert "1.0.0" in applied

    def test_set_error_with_non_string(self):
        """Test set_error with non-string error_message."""
        result = MigrateResult()
        result.set_error(None)

        assert result.success is False
        assert result.error_message is None


@pytest.mark.unit
class TestOperationResultExtended:
    """Extended tests for OperationResult."""

    def test_init_with_error_and_error_message(self):
        """Test init with both error and error_message (error takes precedence)."""
        result = OperationResult(error="error_param", error_message="error_message_param")

        assert result.error_message == "error_param"

    def test_execution_time_negative_delta(self):
        """Test execution_time with negative delta (shouldn't happen but test edge case)."""
        result = OperationResult()
        result.start_time = datetime(2023, 1, 1, 12, 0, 0)
        result.end_time = datetime(2023, 1, 1, 11, 0, 0)  # Before start_time

        execution_time = result.execution_time()

        # Should return 0 or negative value (implementation dependent)
        assert isinstance(execution_time, int)
