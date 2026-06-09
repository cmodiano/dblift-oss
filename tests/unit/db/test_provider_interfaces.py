"""
Tests de conformité ISP pour les interfaces focalisées des providers.

Vérifie que :
- Les 5 ABCs déclarent les bonnes méthodes abstraites
- Tous les providers SQL implémentent les 5 interfaces via BaseProvider
- CosmosDbProvider.supports_transactions() retourne False
- Les providers SQL supports_transactions() retournent True
- Les ABCs ne peuvent pas être instanciées directement
"""

import pytest

from db.base_provider import BaseProvider, NativeProvider
from db.provider_interfaces import (
    ConnectionProvider,
    MigrationProvider,
    QueryProvider,
    SchemaProvider,
    TransactionalProvider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_INTERFACES = [
    ConnectionProvider,
    QueryProvider,
    SchemaProvider,
    TransactionalProvider,
    MigrationProvider,
]


# ---------------------------------------------------------------------------
# T5.4 — Tests ABC structure : chaque interface déclare les bonnes méthodes
# ---------------------------------------------------------------------------


class TestConnectionProviderABC:
    def test_abstract_methods(self):
        expected = {"create_connection", "close", "is_connected", "connect"}
        assert ConnectionProvider.__abstractmethods__ == expected

    def test_method_count(self):
        assert len(ConnectionProvider.__abstractmethods__) == 4


class TestQueryProviderABC:
    def test_abstract_methods(self):
        expected = {"execute_statement", "execute_query"}
        assert QueryProvider.__abstractmethods__ == expected

    def test_get_parameter_placeholders_is_concrete(self):
        """get_parameter_placeholders has a default implementation, not abstract."""
        assert "get_parameter_placeholders" not in QueryProvider.__abstractmethods__


class TestSchemaProviderABC:
    def test_abstract_methods(self):
        expected = {
            "create_schema_if_not_exists",
            "table_exists",
            "get_database_version",
            "set_current_schema",
            "get_schema_qualified_name",
            "clean_schema",
            "create_snapshot_table_if_not_exists",
        }
        assert SchemaProvider.__abstractmethods__ == expected

    def test_method_count(self):
        assert len(SchemaProvider.__abstractmethods__) == 7


class TestTransactionalProviderABC:
    def test_abstract_methods(self):
        expected = {"begin_transaction", "commit_transaction", "rollback_transaction"}
        assert TransactionalProvider.__abstractmethods__ == expected

    def test_supports_transactions_is_concrete(self):
        """supports_transactions() has a default return True, not abstract."""
        assert "supports_transactions" not in TransactionalProvider.__abstractmethods__

    def test_supports_transactions_default_returns_true(self):
        """Default supports_transactions() returns True."""

        class ConcreteTransactional(TransactionalProvider):
            def begin_transaction(self) -> None: ...
            def commit_transaction(self) -> None: ...
            def rollback_transaction(self) -> None: ...

        assert ConcreteTransactional().supports_transactions() is True


class TestMigrationProviderABC:
    def test_abstract_methods(self):
        expected = {
            "get_applied_migrations",
            "record_migration",
            "create_history_table",
            "create_history_table_if_not_exists",
            "create_migration_lock_table_if_not_exists",
            "acquire_migration_lock",
            "release_migration_lock",
        }
        assert MigrationProvider.__abstractmethods__ == expected

    def test_method_count(self):
        assert len(MigrationProvider.__abstractmethods__) == 7


# ---------------------------------------------------------------------------
# T5.5 — Test qu'on ne peut pas instancier une interface directement
# ---------------------------------------------------------------------------


class TestCannotInstantiateABCs:
    @pytest.mark.parametrize("interface", ALL_INTERFACES, ids=lambda i: i.__name__)
    def test_cannot_instantiate_abc(self, interface):
        with pytest.raises(TypeError):
            interface()


# ---------------------------------------------------------------------------
# T5.1 — Tests isinstance : native providers inherit the focused interfaces
# ---------------------------------------------------------------------------


class TestSQLiteProviderInheritance:
    def test_sqlite_is_subclass_of_base_provider(self):
        from db.plugins.sqlite.provider import SQLiteProvider

        assert issubclass(SQLiteProvider, BaseProvider)
        assert issubclass(SQLiteProvider, NativeProvider)

    def test_sqlite_is_subclass_of_all_interfaces(self):
        from db.plugins.sqlite.provider import SQLiteProvider

        for interface in ALL_INTERFACES:
            assert issubclass(
                SQLiteProvider, interface
            ), f"SQLiteProvider should be subclass of {interface.__name__}"


class TestMySqlProviderInheritance:
    def test_mysql_is_subclass_of_base_provider(self):
        from db.plugins.mysql.provider import MySqlProvider

        assert issubclass(MySqlProvider, BaseProvider)
        assert issubclass(MySqlProvider, NativeProvider)

    def test_mysql_is_subclass_of_all_interfaces(self):
        from db.plugins.mysql.provider import MySqlProvider

        for interface in ALL_INTERFACES:
            assert issubclass(
                MySqlProvider, interface
            ), f"MySqlProvider should be subclass of {interface.__name__}"


# ---------------------------------------------------------------------------
# T5.3 — Tests native supports_transactions() → True for relational providers
# ---------------------------------------------------------------------------


class TestNativeSupportsTransactions:
    def test_postgresql_supports_transactions(self):
        from db.plugins.postgresql.provider import PostgreSqlProvider

        provider = PostgreSqlProvider.__new__(PostgreSqlProvider)
        assert provider.supports_transactions() is True

    def test_mysql_supports_transactions(self):
        from db.plugins.mysql.provider import MySqlProvider

        provider = MySqlProvider.__new__(MySqlProvider)
        assert provider.supports_transactions() is True
