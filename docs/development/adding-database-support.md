# Adding Database Support

Adding a new database to dblift requires creating **one plugin folder** — no file
outside `db/plugins/<dialect>/` needs to change.  The plugin folder is discovered
automatically at runtime via Python entry-points.

This guide walks through the complete process and the acceptance criteria that
confirm the isolation guarantee.

---

## Prerequisites

- Understand the [`DialectQuirks` hook surface](../architecture/database-providers.md#dialectquirks--the-plugins-behaviour-contract)
- Know the database's SQLAlchemy URL format or Python SDK
- Have a local instance of the database for testing

---

## Step 1 — Create the plugin folder

```bash
mkdir -p db/plugins/mydb/generator db/plugins/mydb/parser
touch db/plugins/mydb/__init__.py
```

---

## Step 2 — Write `quirks.py`

`quirks.py` is the single file that controls all dialect-specific behaviour.
Start with the minimum required attributes; add hooks only for the delta from
the ANSI defaults.

```python
# db/plugins/mydb/quirks.py
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Type
from db.base_quirks import BaseQuirks

if TYPE_CHECKING:
    from core.sql_generator.alter.base_alter_generator import BaseAlterGenerator
    from core.sql_generator.base_generator import BaseSqlGenerator


class MyDbQuirks(BaseQuirks):
    # --- Capability matrix ---------------------------------------------------
    supports_transactions = True
    supports_transactional_ddl = True   # False for MySQL, Oracle
    schema_required = True
    uppercase_identifiers = False       # True for Oracle, DB2
    clean_strategy = "native"

    # --- sqlglot integration -------------------------------------------------
    sqlglot_dialect = "mydb"            # None if sqlglot has no support

    # --- Native URL ----------------------------------------------------------
    native_url_schema_params = ("currentSchema",)
    lint_placeholder_native_url = "mydb+driver://127.0.0.1:5432/dblift_validate_sql"

    # --- Identifier quoting --------------------------------------------------
    quote_open = '"'
    quote_close = '"'

    # --- DROP behaviour ------------------------------------------------------
    drop_supports_if_exists = True

    def __init__(self, dialect_name: str = "mydb") -> None:
        super().__init__(dialect_name=dialect_name)

    # -------------------------------------------------------------------------
    # Generator / parser factory hooks (required)
    # -------------------------------------------------------------------------

    def ddl_generator_class(self) -> Optional[Type["BaseSqlGenerator"]]:
        # Return None to use BasicTableDdlGenerator fallback
        from db.plugins.mydb.generator.ddl_generator import MyDbSqlGenerator
        return MyDbSqlGenerator

    def alter_generator_class(self) -> Optional[Type["BaseAlterGenerator"]]:
        from db.plugins.mydb.generator.alter_generator import MyDbAlterGenerator
        return MyDbAlterGenerator

    def parser_class(self, parser_type: str) -> Optional[type]:
        if parser_type in ("hybrid", "sqlglot"):
            from core.sql_parser.hybrid_parser import HybridParser
            return HybridParser
        if parser_type == "regex":
            from db.plugins.mydb.parser.mydb_regex_parser import MyDbRegexParser
            return MyDbRegexParser
        return None

    # -------------------------------------------------------------------------
    # Column ALTER SQL (required if database has non-ANSI ALTER syntax)
    # -------------------------------------------------------------------------

    def render_column_nullable_change(
        self, col_diff, formatted_table: str, formatted_column: str, dialect: str
    ):
        from core.sql_generator.sql_statement import SqlStatement
        nullable_diff = getattr(col_diff, "nullable_diff", None)
        if nullable_diff is None:
            return None
        expected_nullable, _ = nullable_diff
        verb = "DROP NOT NULL" if expected_nullable else "SET NOT NULL"
        return SqlStatement(
            sql=f"ALTER TABLE {formatted_table} ALTER COLUMN {formatted_column} {verb};",
            statement_type="ALTER",
            object_type="COLUMN",
            object_name=f"{formatted_table}.{formatted_column}",
            dialect=dialect,
        )

    def render_column_type_change(
        self, col_diff, formatted_table: str, formatted_column: str, dialect: str
    ):
        from core.sql_generator.sql_statement import SqlStatement
        data_type_diff = getattr(col_diff, "data_type_diff", None)
        if data_type_diff is None:
            return None
        expected_type, _ = data_type_diff
        return SqlStatement(
            sql=f"ALTER TABLE {formatted_table} ALTER COLUMN {formatted_column} TYPE {expected_type};",
            statement_type="ALTER",
            object_type="COLUMN",
            object_name=f"{formatted_table}.{formatted_column}",
            dialect=dialect,
        )

    # -------------------------------------------------------------------------
    # Other hooks — only override what differs from the ANSI default
    # -------------------------------------------------------------------------

    def render_identity_clause(self, col) -> Optional[str]:
        # Example: return "AUTOINCREMENT" for Snowflake, "AUTO_INCREMENT" for MySQL
        return None

    def round_trip_extra_object_types(self) -> list:
        # Return names of object types your DB supports beyond the base set:
        # "user_defined_types", "materialized_views", "extensions",
        # "synonyms", "packages", "events"
        return []


__all__ = ["MyDbQuirks"]
```

### Key quirks hooks reference

| Hook | When to override |
|---|---|
| `normalize_column_data_type(col, data_type)` | Non-standard type strings in DDL (e.g. SQL Server `IDENTITY` suffix) |
| `render_identity_clause(col)` | Auto-increment syntax (`AUTO_INCREMENT`, `AUTOINCREMENT`, `GENERATED AS IDENTITY`) |
| `render_column_nullable_change(...)` | Non-ANSI `ALTER COLUMN` / `MODIFY` syntax |
| `render_column_default_change(...)` | Non-ANSI DEFAULT change syntax |
| `render_column_type_change(...)` | Non-ANSI type-change syntax |
| `render_column_collation_change(...)` | Non-ANSI collation-change syntax |
| `unwrap_default_value(default_str, col)` | Dialect wraps defaults in parens or quotes |
| `fk_reference_bind_params(schema, table, col)` | FK safety query has non-standard bind params |
| `render_drop_for_object(...)` | Non-standard DROP syntax (Oracle CASCADE CONSTRAINTS) |
| `preprocess_sql_for_sqlglot(sql)` | SQL needs normalisation before sqlglot can parse it |
| `is_sqlglot_opaque_valid_ddl(sql)` | Valid DDL that sqlglot incorrectly rejects |
| `requires_sdk_for_drop()` | Drops require SDK rather than SQL (CosmosDB containers) |
| `round_trip_extra_object_types()` | Dialect-specific object types for round-trip testing |

---

## Step 3 — Write `plugin.py`

```python
# db/plugins/mydb/plugin.py
from db.provider_registry import PluginInfo
from db.plugins.mydb.sqlalchemy_url import build_sqlalchemy_url
from db.plugins.mydb.provider import MyDbProvider
from db.plugins.mydb.quirks import MyDbQuirks

PLUGIN = PluginInfo(
    name="mydb",
    version="1.0.0",
    description="MyDB database provider",
    dialects=["mydb", "my-db"],   # all accepted dialect name variants
    sqlalchemy_url_builder=build_sqlalchemy_url,
    provider_class=MyDbProvider,
    transport="native",
    quirks_class=MyDbQuirks,
)
```

---

## Step 4 — Implement `provider.py`

`provider.py` connects the five provider components.  For relational databases,
inherit from `SqlAlchemyProvider`; for SDK-backed databases, inherit from
`BaseProvider`.

```python
# db/plugins/mydb/provider.py
from db.sqlalchemy_provider import SqlAlchemyProvider
from db.plugins.mydb.connection_manager import MyDbConnectionManager
from db.plugins.mydb.query_executor import MyDbQueryExecutor
from db.plugins.mydb.schema_operations import MyDbSchemaOperations
from db.plugins.mydb.locking_manager import MyDbLockingManager
from db.plugins.mydb.history_manager import MyDbHistoryManager


class MyDbProvider(SqlAlchemyProvider):
    def __init__(self, config, log=None):
        super().__init__(
            config=config,
            log=log,
            connection_manager_class=MyDbConnectionManager,
            query_executor_class=MyDbQueryExecutor,
            schema_operations_class=MyDbSchemaOperations,
            locking_manager_class=MyDbLockingManager,
            history_manager_class=MyDbHistoryManager,
        )
```

### Five components

| Component | Base class | What to implement |
|---|---|---|
| `ConnectionManager` | `BaseConnectionManager` | `create_connection()`, `configure_connection()` |
| `QueryExecutor` | `BaseQueryExecutor` | `execute()`, `execute_statement()` |
| `SchemaOperations` | `BaseSchemaOperations` | `create_schema()`, `schema_exists()`, `clean_schema()` |
| `LockingManager` | `BaseLockingManager` | `acquire_lock()`, `release_lock()`, `create_lock_table()` |
| `HistoryManager` | `BaseHistoryManager` | records and reads `dblift_schema_history` rows |

---

## Step 5 — Register the entry-point

Add one line to `pyproject.toml`:

```toml
[project.entry-points."dblift.providers"]
# ... existing dialects ...
mydb = "db.plugins.mydb.plugin:PLUGIN"
```

After `pip install -e .`, the plugin is discovered automatically.

---

## Step 6 — Write the DDL and ALTER generators

For most dialects the `BasicTableDdlGenerator` fallback is sufficient for CREATE TABLE.
Only override when the dialect's DDL syntax differs significantly.

```python
# db/plugins/mydb/generator/ddl_generator.py
from core.sql_generator.base_generator import BaseSqlGenerator


class MyDbSqlGenerator(BaseSqlGenerator):
    """MyDB DDL generator — override only dialect-specific methods."""

    # The base class handles most cases via quirks hooks.
    # Override generate_create_statement() only if needed.
```

```python
# db/plugins/mydb/generator/alter_generator.py
from core.sql_generator.alter.base_alter_generator import BaseAlterGenerator


class MyDbAlterGenerator(BaseAlterGenerator):
    pass  # Base handles ALTER TABLE via quirks hooks
```

---

## Step 7 — Write or reuse a parser

For SQL dialects with standard syntax, reuse `HybridParser`:

```python
# quirks.py — already done in Step 2
def parser_class(self, parser_type: str):
    if parser_type in ("hybrid", "sqlglot"):
        from core.sql_parser.hybrid_parser import HybridParser
        return HybridParser
    return None
```

For dialects with non-standard syntax (e.g. PL/SQL blocks, SQL\*Plus directives),
write a regex parser inheriting from `BaseRegexParser` and register it under
`parser_type == "regex"`.

---

## Step 8 — Add tests

### Conformance test

The existing `tests/unit/db/test_dialect_quirks_conformance.py` runs against
`KNOWN_DIALECTS`.  Add your dialect to the list and all hook-coverage assertions
run automatically:

```python
KNOWN_DIALECTS = (
    "postgresql", "mysql", ...,
    "mydb",   # ← add here
)
```

### Unit tests

Create `tests/unit/db/plugins/mydb/` with tests covering:

- `TestMyDbQuirks` — hook return values
- `TestMyDbProvider` — connection lifecycle (mocked native driver / SQLAlchemy engine)
- `TestMyDbGenerator` — DDL output for CREATE TABLE, DROP TABLE, ALTER TABLE

### Integration test matrix

Add `mydb` to the dialect matrix in `tests/integration/matrix/` when a live
database is available.

---

## Step 9 — Verify isolation

After implementing, confirm zero core edits are needed:

```bash
# 1. Lint baseline must stay at 0
python3 scripts/lint_patterns.py

# 2. Conformance tests pass for your new dialect
python3 -m pytest tests/unit/db/test_dialect_quirks_conformance.py -v

# 3. Full unit suite green
python3 -m pytest tests/unit/ -n auto -q

# 4. Verify no core/ file was touched
git diff --name-only HEAD | grep -v '^db/plugins/mydb\|^pyproject.toml\|^tests/'
# Expected: empty output (no core/ changes)
```

---

## Common patterns

### Dialect inherits from another (e.g. MariaDB from MySQL)

```python
from db.plugins.mysql.quirks import MysqlQuirks

class MariadbQuirks(MysqlQuirks):
    def __init__(self, dialect_name: str = "mariadb") -> None:
        super().__init__(dialect_name=dialect_name)
    # Override only the deltas
```

### Schema-less / NoSQL database

```python
class MyNoSqlQuirks(BaseQuirks):
    is_nosql = True
    schema_required = False
    default_schema_name = "default"

    def requires_sdk_for_drop(self) -> bool:
        return True  # DROP operations go through the SDK, not SQL

    def sdk_operation_hint_prefix(self) -> Optional[str]:
        return "-- [MYNOSQL SDK OPERATION]"

    # Column ALTER operations are not applicable — return comment
    def render_column_nullable_change(self, col_diff, table, col, dialect):
        from core.sql_generator.sql_statement import SqlStatement
        return SqlStatement(
            sql=f"-- Schema-less: nullable not applicable for {table}.{col}",
            statement_type="COMMENT",
            object_type="COLUMN",
            object_name=f"{table}.{col}",
            dialect=dialect,
        )
```

### Oracle-style MODIFY syntax

All ALTER COLUMN operations use `MODIFY col TYPE` instead of `ALTER COLUMN col TYPE`:

```python
def render_column_type_change(self, col_diff, table, col, dialect):
    from core.sql_generator.sql_statement import SqlStatement
    expected_type, _ = getattr(col_diff, "data_type_diff", (None, None))
    if expected_type is None:
        return None
    return SqlStatement(
        sql=f"ALTER TABLE {table} MODIFY {col} {expected_type};",
        statement_type="ALTER", object_type="COLUMN",
        object_name=f"{table}.{col}", dialect=dialect,
    )
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `get_quirks("mydb")` returns `BaseQuirks` | Plugin not discovered | Check `pyproject.toml` entry-point; run `pip install -e .` |
| `ProviderRegistry.create_provider("mydb", ...)` fails | `provider_class` not set in `PluginInfo` | Set `provider_class=MyDbProvider` in `plugin.py` |
| `scripts/lint_patterns.py` reports new violations | Dialect string in core/ | Remove; route through quirks hook instead |
| Conformance test fails for new hook | Quirks method returns wrong type | Return `None`, `str`, or `SqlStatement` — check BaseQuirks docstring |
| Generator produces wrong DDL | `ddl_generator_class()` returns `None` | Implement `MyDbSqlGenerator` or return `None` for BasicTableDdlGenerator fallback |

---

## Reference

- `db/base_quirks.py` — complete hook reference with docstrings
- `db/plugins/postgresql/` — most complete first-party example
- `db/plugins/mariadb/` — minimal example (inherits MySQL)
- `db/plugins/cosmosdb/` — native SDK example
- [ADR-0026](../adr/0026-dialect-plugin-isolation.md) — architecture decision
- [ADR-0027](../adr/0027-generator-isolation.md) — generator isolation decision
- [Database providers](../architecture/database-providers.md) — system overview
