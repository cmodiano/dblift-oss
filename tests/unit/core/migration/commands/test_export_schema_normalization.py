"""Tests for _normalize_schema_for_dialect() utility function."""

import unittest
from unittest.mock import MagicMock

from core.migration.commands.export_schema_command import (
    ExportSchemaOptions,
    SchemaExporter,
    _normalize_schema_for_dialect,
)


class TestNormalizeSchemaForDialect(unittest.TestCase):
    """AC#8: At least 8 direct tests covering _normalize_schema_for_dialect()."""

    # --- Oracle / DB2: uppercase ---

    def test_oracle_uppercase(self):
        """Oracle dialect normalizes schema to uppercase."""
        result = _normalize_schema_for_dialect("my_schema", "oracle")
        self.assertEqual(result, "MY_SCHEMA")

    def test_db2_uppercase(self):
        """DB2 dialect normalizes schema to uppercase."""
        result = _normalize_schema_for_dialect("my_schema", "db2")
        self.assertEqual(result, "MY_SCHEMA")

    # --- PostgreSQL ---

    def test_postgresql_default_public_when_none(self):
        """PostgreSQL defaults to 'public' when schema is None."""
        result = _normalize_schema_for_dialect(None, "postgresql")
        self.assertEqual(result, "public")

    def test_postgresql_default_public_when_empty(self):
        """PostgreSQL defaults to 'public' when schema is empty string."""
        result = _normalize_schema_for_dialect("", "postgresql")
        self.assertEqual(result, "public")

    def test_postgresql_non_public_value(self):
        """PostgreSQL with non-public schema returns lowercase."""
        result = _normalize_schema_for_dialect("MySchema", "postgresql")
        self.assertEqual(result, "myschema")

    def test_postgresql_public_stays_public(self):
        """PostgreSQL 'public' (any case) normalizes to 'public'."""
        result = _normalize_schema_for_dialect("PUBLIC", "postgresql")
        self.assertEqual(result, "public")

    # --- CosmosDB ---

    def test_cosmosdb_default_when_none(self):
        """CosmosDB defaults to 'default' when schema is None."""
        result = _normalize_schema_for_dialect(None, "cosmosdb")
        self.assertEqual(result, "default")

    def test_cosmosdb_default_when_empty(self):
        """CosmosDB defaults to 'default' when schema is empty string."""
        result = _normalize_schema_for_dialect("", "cosmosdb")
        self.assertEqual(result, "default")

    def test_cosmosdb_existing_value(self):
        """CosmosDB with existing non-default schema returns lowercase."""
        result = _normalize_schema_for_dialect("MyContainer", "cosmosdb")
        self.assertEqual(result, "mycontainer")

    def test_cosmosdb_default_value_stays_default(self):
        """CosmosDB 'default' (any case) normalizes to 'default'."""
        result = _normalize_schema_for_dialect("DEFAULT", "cosmosdb")
        self.assertEqual(result, "default")

    # --- MySQL / others ---

    def test_mysql_lowercase(self):
        """MySQL (other dialect) normalizes to lowercase."""
        result = _normalize_schema_for_dialect("MyDB", "mysql")
        self.assertEqual(result, "mydb")

    def test_none_without_dialect(self):
        """None schema with unknown dialect returns empty string."""
        result = _normalize_schema_for_dialect(None, "")
        self.assertEqual(result, "")

    def test_empty_schema_unknown_dialect(self):
        """Empty schema with unknown dialect returns empty string."""
        result = _normalize_schema_for_dialect("", "unknown")
        self.assertEqual(result, "")

    # --- Edge cases ---

    def test_whitespace_only_treated_as_empty(self):
        """Whitespace-only schema treated as empty (PostgreSQL → 'public')."""
        result = _normalize_schema_for_dialect("   ", "postgresql")
        self.assertEqual(result, "public")

    def test_schema_with_leading_trailing_spaces_stripped(self):
        """Schema with leading/trailing spaces is stripped before normalization."""
        result = _normalize_schema_for_dialect("  MY_SCHEMA  ", "oracle")
        self.assertEqual(result, "MY_SCHEMA")


class TestNormalizeObjectSchemaDelegation(unittest.TestCase):
    """AC#2: _normalize_object_schema() delegates to _normalize_schema_for_dialect()."""

    def _make_exporter(self, dialect: str) -> SchemaExporter:
        config = MagicMock()
        config.database.type = dialect
        options = MagicMock(spec=ExportSchemaOptions)
        return SchemaExporter(config=config, options=options)

    def test_delegates_oracle_uppercase(self):
        """_normalize_object_schema uses config.database.type for Oracle uppercase."""
        exporter = self._make_exporter("oracle")
        self.assertEqual(exporter._normalize_object_schema("my_schema"), "MY_SCHEMA")

    def test_delegates_postgresql_default(self):
        """_normalize_object_schema uses config.database.type for PostgreSQL default."""
        exporter = self._make_exporter("postgresql")
        self.assertEqual(exporter._normalize_object_schema(None), "public")

    def test_delegates_none_type_returns_empty(self):
        """_normalize_object_schema handles config.database.type=None via or ''."""
        exporter = self._make_exporter(None)
        self.assertEqual(exporter._normalize_object_schema("my_schema"), "my_schema")


if __name__ == "__main__":
    unittest.main()
