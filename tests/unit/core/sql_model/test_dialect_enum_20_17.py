"""Tests for DialectEnum (story 20-17)."""

import pytest

from core.sql_model.dialect import DialectEnum

pytestmark = [pytest.mark.unit]


class TestDialectEnumValues:
    """AC#1.1 — Verify each DialectEnum value is correct."""

    def test_postgresql(self):
        assert DialectEnum.POSTGRESQL == "postgresql"

    def test_oracle(self):
        assert DialectEnum.ORACLE == "oracle"

    def test_mysql(self):
        assert DialectEnum.MYSQL == "mysql"

    def test_sqlserver(self):
        assert DialectEnum.SQLSERVER == "sqlserver"

    def test_db2(self):
        assert DialectEnum.DB2 == "db2"

    def test_sqlite(self):
        assert DialectEnum.SQLITE == "sqlite"

    def test_cosmosdb(self):
        assert DialectEnum.COSMOSDB == "cosmosdb"

    def test_unknown(self):
        assert DialectEnum.UNKNOWN == "unknown"


class TestDialectEnumFromString:
    """AC#1.3 — from_string normalizes and handles unknowns."""

    def test_case_insensitive_oracle(self):
        assert DialectEnum.from_string("Oracle") == DialectEnum.ORACLE

    def test_case_insensitive_postgresql(self):
        assert DialectEnum.from_string("POSTGRESQL") == DialectEnum.POSTGRESQL

    def test_case_insensitive_mysql(self):
        assert DialectEnum.from_string("MySQL") == DialectEnum.MYSQL

    def test_unknown_dialect(self):
        assert DialectEnum.from_string("unknown_db") == DialectEnum.UNKNOWN

    def test_empty_string(self):
        assert DialectEnum.from_string("") == DialectEnum.UNKNOWN

    def test_none_input(self):
        assert DialectEnum.from_string(None) == DialectEnum.UNKNOWN

    def test_whitespace_stripped(self):
        assert DialectEnum.from_string("  postgresql  ") == DialectEnum.POSTGRESQL


class TestDialectEnumImportable:
    """AC#1.4 + AC#1.5 — DialectEnum importable from core.sql_model."""

    def test_importable_from_package(self):
        from core.sql_model import DialectEnum as DE

        assert DE.POSTGRESQL == "postgresql"

    def test_in_all(self):
        import core.sql_model as mod

        assert "DialectEnum" in mod.__all__

    def test_str_enum_equality(self):
        """AC#1.2 — str mixin ensures equality with plain strings."""
        assert DialectEnum.POSTGRESQL == "postgresql"
        assert "postgresql" == DialectEnum.POSTGRESQL

    def test_dict_lookup_with_string_key(self):
        """Dispatch dict .get(self.dialect) works with plain string."""
        dispatch = {DialectEnum.POSTGRESQL: "pg_handler"}
        assert dispatch.get("postgresql") == "pg_handler"
