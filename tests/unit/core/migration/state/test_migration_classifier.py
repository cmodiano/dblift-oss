"""Unit tests for core.migration.state.migration_classifier module."""

from unittest.mock import MagicMock

import pytest

from core.migration.state.migration_classifier import MigrationClassifier


@pytest.mark.unit
class TestMigrationClassifier:
    """Test MigrationClassifier class."""

    def test_initialization(self):
        """Test MigrationClassifier initialization."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        assert classifier.logger == logger

    def test_get_category_and_type_versioned(self):
        """Test get_category_and_type for SQL type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("SQL")

        assert category == "Versioned"
        assert display_type == "Versioned"

    def test_get_category_and_type_repeatable(self):
        """Test get_category_and_type for REPEATABLE type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("REPEATABLE")

        assert category == "Repeatable"
        assert display_type == "Repeatable"

    def test_get_category_and_type_undo_sql(self):
        """Test get_category_and_type for UNDO_SQL type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("UNDO_SQL")

        assert category == "Undo"
        assert display_type == "Undo SQL"

    def test_get_category_and_type_baseline(self):
        """Test get_category_and_type for BASELINE type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("BASELINE")

        assert category == "Baseline"
        assert display_type == "Baseline"

    def test_get_category_and_type_delete(self):
        """Test get_category_and_type for DELETE type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("DELETE")

        assert category == "Deleted"
        assert display_type == "Deleted"

    def test_get_category_and_type_delete_with_description(self):
        """Test get_category_and_type for DELETE with description containing original type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Migration [DELETE:SQL]"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        assert category == "Versioned"
        assert display_type == "Versioned"

    def test_get_category_and_type_delete_with_repeatable_in_description(self):
        """Test DELETE with REPEATABLE in description."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Migration [DELETE:REPEATABLE]"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        assert category == "Repeatable"
        assert display_type == "Repeatable"

    def test_get_category_and_type_delete_with_undo_in_description(self):
        """Test DELETE with UNDO_SQL in description."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Migration [DELETE:UNDO_SQL]"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        assert category == "Undo"
        assert display_type == "Undo SQL"

    def test_get_category_and_type_delete_with_invalid_description(self):
        """Test DELETE with invalid description format."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Migration [DELETE:"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        # Should fall back to script name or default
        assert category in ["Deleted", "Versioned", "Repeatable", "Undo"]

    def test_get_category_and_type_delete_with_v_prefix_script(self):
        """Test DELETE with V-prefixed script name."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Some description"
        migration.script_name = "V1_0_0__create_users.sql"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        assert category == "Versioned"
        assert display_type == "Versioned"

    def test_get_category_and_type_delete_with_r_prefix_script(self):
        """Test DELETE with R-prefixed script name."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Some description"
        migration.script_name = "R__create_indexes.sql"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        assert category == "Repeatable"
        assert display_type == "Repeatable"

    def test_get_category_and_type_delete_with_u_prefix_script(self):
        """Test DELETE with U-prefixed script name."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        migration = MagicMock()
        migration.description = "Some description"
        migration.script_name = "U1_0_0__create_users.sql"
        category, display_type = classifier.get_category_and_type("DELETE", migration)

        assert category == "Undo"
        assert display_type == "Undo SQL"

    def test_get_category_and_type_unknown_type(self):
        """Test get_category_and_type for unknown type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("UNKNOWN_TYPE")

        assert category == "Unknown_type"
        assert display_type == "Unknown_type"

    def test_get_category_and_type_empty_type(self):
        """Test get_category_and_type for empty type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type("")

        assert category == "Unknown"
        assert display_type == "Unknown"

    def test_get_category_and_type_none_type(self):
        """Test get_category_and_type for None type."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category, display_type = classifier.get_category_and_type(None)

        assert category == "Unknown"
        assert display_type == "Unknown"

    def test_get_category_and_type_case_insensitive(self):
        """Test get_category_and_type is case-insensitive."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        category1, _ = classifier.get_category_and_type("versioned")
        category2, _ = classifier.get_category_and_type("SQL")
        category3, _ = classifier.get_category_and_type("Versioned")

        assert category1 == category2 == category3 == "Versioned"

    def test_format_category_basic(self):
        """Test _format_category method."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        formatted = classifier._format_category("test")
        assert formatted == "Test"

    def test_format_category_empty(self):
        """Test _format_category with empty string."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        formatted = classifier._format_category("")
        assert formatted == ""

    def test_format_category_single_letter(self):
        """Test _format_category with single letter."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        formatted = classifier._format_category("a")
        assert formatted == "A"

    def test_format_category_already_formatted(self):
        """Test _format_category with already formatted string."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        formatted = classifier._format_category("Test")
        assert formatted == "Test"

    def test_format_category_uppercase(self):
        """Test _format_category with uppercase string."""
        logger = MagicMock()
        classifier = MigrationClassifier(logger)

        formatted = classifier._format_category("TEST")
        assert formatted == "Test"
