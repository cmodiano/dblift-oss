# 0027 — Generator isolation: last dialect branches into plugin quirks

- Status: Done
- Date: 2026-05-05
- Deciders: Maintainers

## Context and problem statement

After Epic 26 (ADR-0026), `core/sql_generator/` still contained five
categories of hardcoded dialect branches that violated the isolation
goal. Adding a new database required editing four core files regardless
of Epic 26's plugin architecture:

1. `basic_table_ddl_generator._normalize_column_data_type` — per-dialect
   type-string transformations (SQL Server IDENTITY suffix, DB2
   TIMESTAMP precision, PostgreSQL float/timestamp reordering).
2. `basic_table_ddl_generator._build_identity_clause` + `_IDENTITY_STRATEGIES`
   dict — static dispatch map for AUTO_INCREMENT / GENERATED AS IDENTITY
   / IDENTITY(seed,increment).
3. `diff_to_sql.generate_sql_script` + `script_formatter._format_statement`
   — hardcoded `dialect == "cosmosdb"` guards for SDK execution and
   script annotation.
4. `safety_checker._get_fk_reference_query` — hardcoded
   `dialect in {"oracle"}` for the 4-parameter FK lookup (Oracle's
   query references `owner` twice).
5. `basic_table_ddl_generator._format_default_value` — per-dialect
   default-value unwrapping (SQL Server outer-paren strip, MySQL
   backtick/double-quote normalisation).

## Decision

Move each branch into a new hook method on `BaseQuirks` (Epic 26's
dialect plugin base class). Core calls the hook; the dialect plugin
overrides the delta. Default implementations are no-ops or return the
input unchanged so unregistered dialects degrade gracefully.

### New hooks

| Hook | Default | Overriding plugins |
|---|---|---|
| `normalize_column_data_type(col, data_type)` | passthrough | PostgreSQL, SQL Server, DB2 |
| `render_identity_clause(col)` | `None` | PostgreSQL, SQL Server, DB2, Oracle, MySQL/MariaDB |
| `fk_reference_bind_params(schema, table, col)` | `[s, t, c]` | Oracle (4-item) |
| `requires_sdk_for_drop()` | `False` | CosmosDB |
| `sdk_operation_hint_prefix()` | `None` | CosmosDB |
| `unwrap_default_value(default_str, col)` | passthrough | SQL Server, MySQL |

### Removed from core

- Module-level `_identity_db2 / _identity_oracle / _identity_sqlserver /
  _identity_mysql / _identity_postgresql` functions.
- `_IDENTITY_STRATEGIES` dispatch dict (`Dict[str, Callable]`).
- All `if dialect == "cosmosdb"`, `if dialect == "sqlserver"`,
  `if dialect == "db2"`, `if dialect in {"oracle"}` branches from the
  six affected methods.

## Consequences

### Positive

- **Zero core edits for new dialects.** After this ADR, adding a
  database requires only: `db/plugins/<X>/quirks.py`,
  `db/plugins/<X>/plugin.py`, and a `pyproject.toml` entry-point. No
  file in `core/`, `api/`, `cli/`, or `config/` needs to change.
- **Conformance tests enforce the boundary.** Each hook is covered by
  a parametrised assertion in
  `tests/unit/db/test_dialect_quirks_conformance.py`; any regression
  where a new dialect produces wrong output from a default hook will
  fail CI immediately.
- **Flyway parity on the generator layer.** Like Flyway's
  `Database.getRawCreateScript()` and `DatabaseType.createParser()`,
  core now delegates all dialect-specific rendering to the plugin — it
  never names a dialect.

### Negative

- Six new methods on `BaseQuirks` increase the protocol surface. Each
  method has a safe default, so existing plugins without an override are
  unaffected; but maintainers of external plugins must be aware of the
  new extension points.

## Verification

```bash
# Conformance tests
python3 -m pytest tests/unit/db/test_dialect_quirks_conformance.py -v

# Lint baseline (must stay 0)
python3 scripts/lint_patterns.py

# Full suite
python3 -m pytest tests/unit/ -n auto -q
```

## References

- Epic 26 plan: `docs/architecture/EPIC-26-dialect-plugin-isolation.md`
- Epic 27 plan: `docs/architecture/EPIC-27-generator-isolation.md`
- ADR-0026 — Dialect plugin isolation (prerequisite)
- ADR-0007 — Dialect capabilities matrix
