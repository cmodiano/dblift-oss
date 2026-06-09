"""
Unit tests for IdentifierNormalizer.
"""

import pytest

from core.normalization.identifier_normalizer import IdentifierNormalizer, NormalizedIdentifier

pytestmark = [pytest.mark.unit]


class TestIdentifierNormalizer:
    """Test cases for IdentifierNormalizer."""

    def test_normalize_postgresql_unquoted(self):
        """Test PostgreSQL unquoted identifier normalization."""
        normalizer = IdentifierNormalizer("postgresql")

        result = normalizer.normalize("MyTable")
        assert result.normalized == "mytable"
        assert result.original == "MyTable"
        assert result.was_quoted is False
        assert result.case_sensitive is False

    def test_normalize_postgresql_quoted(self):
        """Test PostgreSQL quoted identifier normalization."""
        normalizer = IdentifierNormalizer("postgresql")

        result = normalizer.normalize('"MyTable"')
        assert result.normalized == "MyTable"
        assert result.original == '"MyTable"'
        assert result.was_quoted is True
        assert result.case_sensitive is True

    def test_normalize_oracle_unquoted(self):
        """Test Oracle unquoted identifier normalization (uppercase)."""
        normalizer = IdentifierNormalizer("oracle")

        result = normalizer.normalize("mytable")
        assert result.normalized == "MYTABLE"
        assert result.original == "mytable"
        assert result.was_quoted is False

    def test_normalize_oracle_quoted(self):
        """Test Oracle quoted identifier normalization (preserve case)."""
        normalizer = IdentifierNormalizer("oracle")

        result = normalizer.normalize('"MyTable"')
        assert result.normalized == "MyTable"
        assert result.original == '"MyTable"'
        assert result.was_quoted is True

    def test_normalize_mysql_backticks(self):
        """Test MySQL backtick-quoted identifiers."""
        normalizer = IdentifierNormalizer("mysql")

        result = normalizer.normalize("`MyTable`")
        assert result.normalized == "MyTable"
        assert result.original == "`MyTable`"
        assert result.was_quoted is True

    def test_normalize_sqlserver_brackets(self):
        """Test SQL Server bracket-quoted identifiers."""
        normalizer = IdentifierNormalizer("sqlserver")

        result = normalizer.normalize("[MyTable]")
        assert result.normalized == "MyTable"
        assert result.original == "[MyTable]"
        assert result.was_quoted is True

    def test_normalize_qualified_name(self):
        """Test schema-qualified name normalization."""
        normalizer = IdentifierNormalizer("postgresql")

        obj_norm, schema_norm = normalizer.normalize_qualified_name("public.MyTable")
        assert obj_norm.normalized == "mytable"
        assert schema_norm.normalized == "public"

        obj_norm, schema_norm = normalizer.normalize_qualified_name("MyTable", "public")
        assert obj_norm.normalized == "mytable"
        assert schema_norm.normalized == "public"

    def test_denormalize_postgresql(self):
        """Test converting normalized identifier back to SQL format."""
        normalizer = IdentifierNormalizer("postgresql")

        norm_id = NormalizedIdentifier(
            normalized="mytable",
            original="MyTable",
            was_quoted=False,
            case_sensitive=False,
        )
        result = normalizer.denormalize(norm_id)
        assert result == "mytable"

        # Force quotes
        result = normalizer.denormalize(norm_id, force_quotes=True)
        assert result == '"mytable"'

    def test_denormalize_quoted(self):
        """Test denormalizing quoted identifiers."""
        normalizer = IdentifierNormalizer("postgresql")

        norm_id = NormalizedIdentifier(
            normalized="MyTable",
            original='"MyTable"',
            was_quoted=True,
            case_sensitive=True,
        )
        result = normalizer.denormalize(norm_id)
        assert result == '"MyTable"'

    def test_compare_identifiers(self):
        """Test identifier comparison."""
        normalizer = IdentifierNormalizer("postgresql")

        # Case-insensitive comparison
        assert normalizer.compare_identifiers("MyTable", "mytable") is True
        assert normalizer.compare_identifiers("MyTable", "MYTABLE") is True

        # Case-sensitive comparison
        assert normalizer.compare_identifiers("MyTable", "MyTable", case_sensitive=True) is True
        assert normalizer.compare_identifiers("MyTable", "mytable", case_sensitive=True) is False

    def test_should_quote(self):
        """Test determining if identifier should be quoted."""
        # Special characters
        assert IdentifierNormalizer.should_quote("my-table", "postgresql") is True
        assert IdentifierNormalizer.should_quote("my table", "postgresql") is True

        # Reserved words
        assert IdentifierNormalizer.should_quote("select", "postgresql") is True
        assert IdentifierNormalizer.should_quote("table", "postgresql") is True

        # Normal identifiers
        assert IdentifierNormalizer.should_quote("mytable", "postgresql") is False
        assert IdentifierNormalizer.should_quote("my_table", "postgresql") is False

    def test_get_quote_chars(self):
        """Test getting quote characters for dialects."""
        assert IdentifierNormalizer.get_quote_chars("postgresql") == ('"', '"')
        assert IdentifierNormalizer.get_quote_chars("oracle") == ('"', '"')
        assert IdentifierNormalizer.get_quote_chars("mysql") == ("`", "`")
        assert IdentifierNormalizer.get_quote_chars("sqlserver") == ("[", "]")
        assert IdentifierNormalizer.get_quote_chars("db2") == ('"', '"')

    def test_normalized_identifier_to_sql(self):
        """Test NormalizedIdentifier.to_sql() method."""
        # Unquoted, not case-sensitive
        norm_id = NormalizedIdentifier(
            normalized="mytable",
            original="MyTable",
            was_quoted=False,
            case_sensitive=False,
        )
        assert norm_id.to_sql("postgresql") == "mytable"
        assert norm_id.to_sql("postgresql", force_quotes=True) == '"mytable"'

        # Quoted, case-sensitive
        norm_id = NormalizedIdentifier(
            normalized="MyTable",
            original='"MyTable"',
            was_quoted=True,
            case_sensitive=True,
        )
        assert norm_id.to_sql("postgresql") == '"MyTable"'
        assert norm_id.to_sql("mysql") == "`MyTable`"
        assert norm_id.to_sql("sqlserver") == "[MyTable]"
