# Epic 27 — Generator Isolation: eliminate last core dialect branches

**ADR:** 0027 (to be written)
**Branch:** `epic/generator-isolation`
**Goal:** After Epic 26, adding a new database requires editing 4 core files. After Epic 27, zero.

## Problem statement

Epic 26 achieved 95% dialect isolation. Three categories of dialect-specific code remain in
`core/sql_generator/` that break the Flyway model:

| File | Lines | Issue |
|---|---|---|
| `core/sql_generator/basic_table_ddl_generator.py` | 532, 538, 542, 1009 | Type normalization and constraint branches per dialect |
| `core/sql_generator/basic_table_ddl_generator.py` | `_IDENTITY_STRATEGIES` dict | Static map — new dialect silently gets None |
| `core/sql_generator/diff_to_sql.py` | 202, 210, 244 | `dialect == "cosmosdb"` SDK checks |
| `core/sql_generator/script_formatter.py` | 120 | `dialect == "cosmosdb"` SDK hint |
| `core/sql_generator/safety_checker.py` | 685 | `dialect in {"oracle"}` FK bind-param branch |

**Test:** after Epic 27, create `db/plugins/snowflake/quirks.py` extending `BaseQuirks` with no
overrides → all generator/safety code works without editing any `core/` file.

---

## Stories

### 27-1 — `normalize_column_data_type` hook

**Scope:** `basic_table_ddl_generator.py` lines 532, 538, 542.

**Current code:**
```python
if dialect and dialect.lower() == "sqlserver":
    if getattr(col, "is_identity", False):
        data_type = re.sub(r"\s+identity\s*$", ...)
    if re.match(r"^datetime\s*\(", data_type, ...):
        data_type = "datetime"
if dialect and dialect.lower() == "db2":
    if data_type.upper().startswith("TIMESTAMP("):
        data_type = "TIMESTAMP"
elif dialect and dialect.lower() in ("postgresql", "postgres"):
    # float type stripping, TIMESTAMP rewriting...
```

**Fix:**
1. Add to `BaseQuirks`: `def normalize_column_data_type(self, col, data_type: str) -> str: return data_type`
2. SQL Server quirks overrides: strip IDENTITY suffix + collapse `datetime(n)` → `datetime`
3. DB2 quirks overrides: collapse `TIMESTAMP(n)` → `TIMESTAMP`
4. PostgreSQL quirks overrides: strip precision from FLOAT4/FLOAT8/REAL/DOUBLE PRECISION/TIMESTAMP* types
5. `basic_table_ddl_generator._normalize_column_type()` becomes: `return quirks.normalize_column_data_type(col, data_type)`

**Acceptance:** lines 532–555 of `basic_table_ddl_generator.py` collapse to one call.

---

### 27-2 — `render_identity_clause` hook

**Scope:** `_IDENTITY_STRATEGIES` static dict in `basic_table_ddl_generator.py`.

**Current code:**
```python
_IDENTITY_STRATEGIES: Dict[str, Callable] = {
    "db2": _identity_db2,
    "oracle": _identity_oracle,
    "sqlserver": _identity_sqlserver,
    "mysql": _identity_mysql,
    "postgresql": _identity_postgresql,
}
```

**Fix:**
1. Add to `BaseQuirks`: `def render_identity_clause(self, col) -> Optional[str]: return None`
2. Each dialect quirks overrides with its current `_identity_*` logic (inline or delegate)
3. `basic_table_ddl_generator._build_identity_clause()` becomes: `return quirks.render_identity_clause(col)`
4. Delete `_IDENTITY_STRATEGIES` dict and the 5 private `_identity_*` functions from core.

**Acceptance:** `_IDENTITY_STRATEGIES` removed; 5 `_identity_*` functions moved to plugin quirks.

---

### 27-3 — `get_sdk_operation_hint` hook + CosmosDB SDK checks

**Scope:** `diff_to_sql.py` lines 202–244, `script_formatter.py` line 120.

**Current code:**
```python
# diff_to_sql.py
if statement.requires_sdk or (
    statement.dialect.lower() == "cosmosdb" and statement.statement_type == "DROP"
):
    statement.requires_sdk = True
    ...

# script_formatter.py
if statement.dialect.lower() == "cosmosdb" and statement.requires_sdk:
    lines.append("-- [COSMOSDB SDK OPERATION]")
```

**Fix:**
1. Add to `BaseQuirks`: `def requires_sdk_for_drop(self) -> bool: return False`
2. Add to `BaseQuirks`: `def sdk_operation_hint_prefix(self) -> Optional[str]: return None`
3. CosmosDB quirks: `requires_sdk_for_drop = True`, `sdk_operation_hint_prefix = "-- [COSMOSDB SDK OPERATION]"`
4. Replace `dialect.lower() == "cosmosdb"` checks with quirks method calls.

**Acceptance:** `"cosmosdb"` string removed from `diff_to_sql.py` and `script_formatter.py`.

---

### 27-4 — `get_fk_reference_bind_params` hook

**Scope:** `safety_checker.py` line 685.

**Current code:**
```python
if self.dialect in frozenset({"oracle"}):
    return (query, [schema, schema, table, column])
return (query, [schema, table, column])
```

**Fix:**
1. Add to `BaseQuirks`: `def fk_reference_bind_params(self, schema: str, table: str, column: str) -> list: return [schema, table, column]`
2. Oracle quirks overrides: `return [schema, schema, table, column]`
3. Replace the branch in `safety_checker.py` with `return (query, quirks.fk_reference_bind_params(schema, table, column))`

**Acceptance:** `frozenset({"oracle"})` removed from `safety_checker.py`.

---

### 27-5 — default value unwrapping hook (line 1009)

**Scope:** `basic_table_ddl_generator.py` line 1009.

**Current code:**
```python
elif self.table.dialect and self.table.dialect.lower() == "sqlserver":
    if default_str.startswith("(") and default_str.endswith(")"):
        inner = default_str[1:-1].strip()
        if not any(op in inner for op in ["+", "-", ...]):
            return inner
```

**Fix:**
1. Add to `BaseQuirks`: `def unwrap_default_value(self, default_str: str) -> str: return default_str`
2. SQL Server quirks overrides: strip outer parens if no operators.
3. Replace branch with `return quirks.unwrap_default_value(default_str)`.

**Acceptance:** `"sqlserver"` string removed from `_get_default_value()` method.

---

### 27-6 — Snowflake PoC + lint baseline confirms 0

**Scope:** Validation that Epic 27 succeeded.

**Tasks:**
1. Create `db/plugins/snowflake/` with `quirks.py` extending `BaseQuirks` (no overrides needed).
2. Create `db/plugins/snowflake/plugin.py` with `PLUGIN = PluginInfo(...)`.
3. Add entry-point to `pyproject.toml`.
4. Run full test suite — 0 failures.
5. Run `scripts/lint_patterns.py` — 0 violations.
6. Verify: no file in `core/` was edited.
7. Write ADR-0027.

**Acceptance:** Snowflake plugin exists and is discovered. Adding it required zero core edits.

---

## Architecture diagram — after Epic 27

```
core/sql_generator/
  basic_table_ddl_generator.py  ← calls quirks.normalize_column_data_type()
                                   calls quirks.render_identity_clause()
                                   calls quirks.unwrap_default_value()
  diff_to_sql.py                ← calls quirks.requires_sdk_for_drop()
  script_formatter.py           ← calls quirks.sdk_operation_hint_prefix()
  safety_checker.py             ← calls quirks.fk_reference_bind_params()

db/plugins/
  postgresql/quirks.py          ← normalize_column_data_type() strips float precision
  sqlserver/quirks.py           ← normalize_column_data_type() + unwrap_default_value()
  db2/quirks.py                 ← normalize_column_data_type() collapses TIMESTAMP(n)
  oracle/quirks.py              ← fk_reference_bind_params() returns [schema,schema,t,c]
  cosmosdb/quirks.py            ← requires_sdk_for_drop=True, sdk_operation_hint_prefix
  mysql/quirks.py               ← render_identity_clause() → AUTO_INCREMENT
  snowflake/quirks.py           ← all defaults (no overrides needed)
```

## Definition of done

- `scripts/lint_patterns.py` → 0 violations (baseline already 0; stays 0)
- Snowflake plugin added with zero core edits
- All existing tests pass (no regressions)
- ADR-0027 written

## Effort estimate

| Story | Effort |
|---|---|
| 27-1 normalize_column_data_type | 1 day |
| 27-2 render_identity_clause | 1 day |
| 27-3 SDK hooks | 0.5 day |
| 27-4 FK bind params | 0.5 day |
| 27-5 default value unwrap | 0.5 day |
| 27-6 Snowflake PoC + ADR | 0.5 day |
| **Total** | **4 days** |
