"""Tests for new BaseQuirks hooks added in dialect-boundary-cleanup.

Story 1: introspector_class, non_transactional_sql_patterns,
         existence_check_sql, fk_reference_query, index_reference_query.
Story 2: IntrospectorFactory quirks-driven registration.
"""

import pytest

from db.base_quirks import BaseQuirks

# ---------------------------------------------------------------------------
# BaseQuirks defaults
# ---------------------------------------------------------------------------


def test_introspector_class_default_returns_none():
    assert BaseQuirks("pg").introspector_class() is None


def test_non_transactional_patterns_default_empty():
    assert BaseQuirks("pg").non_transactional_sql_patterns == ()


def test_existence_check_sql_default_uses_limit():
    sql = BaseQuirks("pg").existence_check_sql("public.orders")
    assert "LIMIT 1" in sql
    assert "public.orders" in sql


def test_fk_reference_query_default_returns_none():
    q, params = BaseQuirks("pg").fk_reference_query("s", "t", "c")
    assert q is None
    assert params == []


def test_index_reference_query_default_returns_none():
    q, params = BaseQuirks("pg").index_reference_query("s", "t", "c")
    assert q is None
    assert params == []


# ---------------------------------------------------------------------------
# Per-DB overrides — introspector_class
# ---------------------------------------------------------------------------


def test_postgresql_introspector_class_returns_plugin_subclass():
    """F.3.a: PostgreSQL's quirks returns its plugin-located
    :class:`PostgreSQLIntrospector` (a thin :class:`SchemaIntrospector`
    subclass that lives in ``db/plugins/postgresql/introspection/``)."""
    from db.plugins.postgresql.introspection.postgresql_introspector import (
        PostgreSQLIntrospector,
    )
    from db.plugins.postgresql.quirks import PostgresqlQuirks

    assert PostgresqlQuirks().introspector_class() is PostgreSQLIntrospector


def test_mysql_introspector_class_returns_plugin_subclass():
    """F.3.b: MySQL's quirks returns :class:`MySQLIntrospector`; MariaDB
    inherits this via :class:`MariadbQuirks(MysqlQuirks)`."""
    from db.plugins.mysql.introspection.mysql_introspector import MySQLIntrospector
    from db.plugins.mysql.quirks import MysqlQuirks

    assert MysqlQuirks().introspector_class() is MySQLIntrospector


def test_sqlite_introspector_class():
    from db.plugins.sqlite.introspection import SQLiteIntrospector
    from db.plugins.sqlite.quirks import SqliteQuirks

    assert SqliteQuirks().introspector_class() is SQLiteIntrospector


# ---------------------------------------------------------------------------
# Per-DB overrides — non_transactional_sql_patterns
# ---------------------------------------------------------------------------


def test_postgresql_has_concurrently_pattern():
    from db.plugins.postgresql.quirks import PostgresqlQuirks

    patterns = [p for p, _ in PostgresqlQuirks().non_transactional_sql_patterns]
    assert any("CONCURRENTLY" in p for p in patterns)


def test_postgresql_has_vacuum_pattern():
    from db.plugins.postgresql.quirks import PostgresqlQuirks

    patterns = [p for p, _ in PostgresqlQuirks().non_transactional_sql_patterns]
    assert any("VACUUM" in p for p in patterns)


# ---------------------------------------------------------------------------
# Per-DB overrides — existence_check_sql
# ---------------------------------------------------------------------------


def test_postgresql_existence_check_uses_limit():
    from db.plugins.postgresql.quirks import PostgresqlQuirks

    sql = PostgresqlQuirks().existence_check_sql('"public"."orders"')
    assert "LIMIT 1" in sql


# ---------------------------------------------------------------------------
# Per-DB overrides — fk_reference_query
# ---------------------------------------------------------------------------


def test_postgresql_fk_query_returns_sql_and_params():
    from db.plugins.postgresql.quirks import PostgresqlQuirks

    sql, params = PostgresqlQuirks().fk_reference_query("myschema", "orders", "user_id")
    assert sql is not None
    assert "FOREIGN KEY" in sql.upper()
    assert params == ["myschema", "orders", "user_id"]


def test_mysql_fk_query_returns_sql():
    from db.plugins.mysql.quirks import MysqlQuirks

    sql, params = MysqlQuirks().fk_reference_query("mydb", "orders", "user_id")
    assert sql is not None
    assert params == ["mydb", "orders", "user_id"]


# ---------------------------------------------------------------------------
# Per-DB overrides — index_reference_query
# ---------------------------------------------------------------------------


def test_mysql_index_query_returns_sql():
    from db.plugins.mysql.quirks import MysqlQuirks

    sql, params = MysqlQuirks().index_reference_query("mydb", "orders", "user_id")
    assert sql is not None
    assert "information_schema" in sql.lower()
    assert params == ["mydb", "orders", "user_id"]


def test_postgresql_index_query_returns_sql():
    from db.plugins.postgresql.quirks import PostgresqlQuirks

    sql, params = PostgresqlQuirks().index_reference_query("myschema", "orders", "user_id")
    assert sql is not None
    assert params == ["myschema", "orders", "user_id"]


# ---------------------------------------------------------------------------
# Story 2: IntrospectorFactory must be quirks-driven
# ---------------------------------------------------------------------------


def test_introspector_factory_uses_quirks():
    """``_register_defaults`` populates the dialect map from each
    quirks' ``introspector_class()``. F.3 wires every plugin to its
    own ``<D>Introspector`` subclass, so every supported dialect now
    appears in the map (no SchemaIntrospector fallback needed)."""
    from core.introspection.introspector_factory import IntrospectorFactory
    from db.plugins.mysql.introspection.mysql_introspector import MySQLIntrospector
    from db.plugins.postgresql.introspection.postgresql_introspector import (
        PostgreSQLIntrospector,
    )
    from db.plugins.sqlite.introspection import SQLiteIntrospector

    IntrospectorFactory._DIALECT_MAP.clear()
    IntrospectorFactory._register_defaults()
    assert IntrospectorFactory._DIALECT_MAP.get("postgresql") is PostgreSQLIntrospector
    assert IntrospectorFactory._DIALECT_MAP.get("mysql") is MySQLIntrospector
    assert IntrospectorFactory._DIALECT_MAP.get("mariadb") is MySQLIntrospector
    assert IntrospectorFactory._DIALECT_MAP.get("sqlite") is SQLiteIntrospector


def test_introspector_factory_hardcoded_strings_absent():
    """_register_defaults must not import any DB module directly."""
    import inspect

    from core.introspection import introspector_factory

    src = inspect.getsource(introspector_factory.IntrospectorFactory._register_defaults)
    for dialect in ("postgresql", "mysql", "sqlite"):
        assert (
            f'"{dialect}"' not in src
        ), f"Hardcoded dialect '{dialect}' found in _register_defaults"
