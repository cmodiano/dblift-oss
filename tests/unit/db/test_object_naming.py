"""Tests for db.object_naming module."""

import pytest

from db.object_naming import (
    LOWERCASE_DIALECTS,
    UPPERCASE_DIALECTS,
    get_normalized_object_name,
)


@pytest.mark.unit
class TestGetNormalizedObjectName:
    """Test get_normalized_object_name function."""

    def test_oracle_uppercase(self):
        """Test Oracle returns UPPERCASE."""
        result = get_normalized_object_name("dblift_schema_history", "oracle")
        assert result == "DBLIFT_SCHEMA_HISTORY"

    def test_db2_uppercase(self):
        """Test DB2 returns UPPERCASE."""
        result = get_normalized_object_name("dblift_schema_history", "db2")
        assert result == "DBLIFT_SCHEMA_HISTORY"

    def test_postgresql_lowercase(self):
        """Test PostgreSQL returns lowercase."""
        result = get_normalized_object_name("DBLIFT_SCHEMA_HISTORY", "postgresql")
        assert result == "dblift_schema_history"

    def test_sqlserver_lowercase(self):
        """Test SQL Server returns lowercase."""
        result = get_normalized_object_name("DBLIFT_SCHEMA_HISTORY", "sqlserver")
        assert result == "dblift_schema_history"

    def test_mysql_lowercase(self):
        """Test MySQL returns lowercase."""
        result = get_normalized_object_name("DBLIFT_SCHEMA_HISTORY", "mysql")
        assert result == "dblift_schema_history"

    def test_sqlite_lowercase(self):
        """Test SQLite returns lowercase."""
        result = get_normalized_object_name("DBLIFT_SCHEMA_HISTORY", "sqlite")
        assert result == "dblift_schema_history"

    def test_cosmosdb_lowercase(self):
        """Test CosmosDB returns lowercase."""
        result = get_normalized_object_name("DBLIFT_SCHEMA_HISTORY", "cosmosdb")
        assert result == "dblift_schema_history"

    def test_case_insensitive_dialect(self):
        """Test dialect matching is case-insensitive."""
        assert get_normalized_object_name("test", "ORACLE") == "TEST"
        assert get_normalized_object_name("test", "Oracle") == "TEST"
        assert get_normalized_object_name("test", "DB2") == "TEST"
        assert get_normalized_object_name("TEST", "PostgreSQL") == "test"

    def test_empty_dialect_defaults_to_lowercase(self):
        """Test empty dialect returns lowercase."""
        result = get_normalized_object_name("TEST", "")
        assert result == "test"

    def test_none_dialect_defaults_to_lowercase(self):
        """Test None dialect returns lowercase."""
        result = get_normalized_object_name("TEST", None)  # type: ignore
        assert result == "test"

    def test_unknown_dialect_defaults_to_lowercase(self):
        """Test unknown dialect returns lowercase."""
        result = get_normalized_object_name("TEST", "unknown_db")
        assert result == "test"

    def test_mixed_case_input_oracle(self):
        """Test mixed case input with Oracle."""
        result = get_normalized_object_name("Dblift_Schema_History", "oracle")
        assert result == "DBLIFT_SCHEMA_HISTORY"

    def test_mixed_case_input_postgresql(self):
        """Test mixed case input with PostgreSQL."""
        result = get_normalized_object_name("Dblift_Schema_History", "postgresql")
        assert result == "dblift_schema_history"


@pytest.mark.unit
class TestDialectSets:
    """Test the dialect constant sets."""

    def test_uppercase_dialects_contains_oracle_and_db2(self):
        """Test UPPERCASE_DIALECTS contains expected databases."""
        assert "oracle" in UPPERCASE_DIALECTS
        assert "db2" in UPPERCASE_DIALECTS

    def test_lowercase_dialects_contains_expected(self):
        """Test LOWERCASE_DIALECTS contains expected databases."""
        assert "postgresql" in LOWERCASE_DIALECTS
        assert "sqlserver" in LOWERCASE_DIALECTS
        assert "mysql" in LOWERCASE_DIALECTS
        assert "sqlite" in LOWERCASE_DIALECTS
        assert "cosmosdb" in LOWERCASE_DIALECTS

    def test_no_overlap_between_sets(self):
        """Test there's no overlap between uppercase and lowercase sets."""
        overlap = UPPERCASE_DIALECTS & LOWERCASE_DIALECTS
        assert len(overlap) == 0, f"Unexpected overlap: {overlap}"
