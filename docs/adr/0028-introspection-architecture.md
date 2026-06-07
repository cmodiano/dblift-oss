[//]: # "0028 — Introspection architecture (extractors + capability gates + per-plugin hooks)"

# 0028 — Introspection architecture

- Status: Accepted
- Date: 2026-05-19
- Deciders: Maintainers
- Extends: ADR 0026 (Dialect plugin isolation), ADR 0027 (Generator isolation)

## Context and problem statement

Pre-Wave F, `db/introspection/` was the second-largest "god class"
hotspot in the codebase after `core/sql_generator/`:

- `SchemaIntrospector` was 1843 LOC. Every `get_X()` method (tables,
  views, sequences, indexes, triggers, procedures, functions, packages,
  synonyms, user-defined types, extensions, foreign data wrappers,
  foreign servers, database links, linked servers, modules, events,
  table partitions) lived inline and switched internally on
  `self.dialect`.
- The five SQL plugin introspectors (`MySQLIntrospector`,
  `PostgreSQLIntrospector`, `OracleIntrospector`,
  `SQLServerIntrospector`, `DB2Introspector`) were "delegation shells"
  that, for every `get_X` call, instantiated a throw-away
  `SchemaIntrospector(...)`, set `temp.dialect = "<x>"`, copied
  `vendor_queries`, called the matching method, and closed it. ~1.7k LOC
  of pure forwarding × 5 dialects.
- The `db/introspection/extractors/` directory existed but only
  partially absorbed the dispatch: `constraint_extractor`,
  `procedure_extractor`, `index_extractor`, etc. each still carried
  `if self.dialect in {"oracle"}:` branches (8–16 each).
- Three flavours of Oracle-only helpers (`_is_oracle_hidden_column`,
  `_normalize_oracle_partition_bound`, `_clean_oracle_source_text`)
  were duplicated across `SchemaIntrospector`, three extractors, and
  the Oracle plugin introspector. A bug fix to one risked drifting
  from the others.
- `VendorPropertyApplier` carried a `_HANDLERS` dispatch dict plus four
  static `_apply_<dialect>_properties` methods. Yet another dialect
  switch in yet another file.
- `core/` and `db/introspection/` had mutual upward leaks:
  `db/introspection/schema_introspector.py` imported `core.licensing._guard`;
  `db/introspection/validation_integration.py` imported
  `core.validation.state_validator`. The introspection layer was supposed
  to be consumed by `core/`, not the other way around.

ADR 0026 established the `DialectQuirks` boundary for DDL generation
and parser dispatch but left introspection untouched. This ADR closes
that gap.

## Decision drivers

- **Plugin isolation invariant**: adding a new dialect must require
  changes only inside `db/plugins/<dialect>/` and
  `db/introspection/databases/<dialect>/`. No file in `core/`,
  `api/`, `cli/`, or `config/` should know about a specific dialect.
- **No upward leaks**: `db/introspection/` is downstream of `core/`,
  so it must not import from `core/validation/`, `core/licensing/`, or
  `core/migration/`. The only legal upward references are
  `core.sql_model`, `core.logger`, `core.constants`.
- **Single source of truth per dialect**: catalog SQL, post-row
  enrichment, helpers — all must live in exactly one place. Duplicated
  copies risk drift.
- **Capability gating**: unsupported object kinds (e.g.
  `get_extensions()` on DB2) must short-circuit without opening a
  provider connection.
- **Test isolation**: per-dialect tests must run independently and
  not pollute a shared registry / cache.

## Considered options

1. **Keep `SchemaIntrospector` as the god class; add hooks as
   needed.** Minimum disruption, but the central file stays huge and
   every new dialect requires editing it.
2. **Move all introspection into plugin-owned subclasses.** Each
   plugin reimplements every `get_X()`. Maximum isolation, but
   ~3-5k LOC duplicated × 7 dialects of mostly identical glue code.
3. **Three-layer architecture: SchemaIntrospector (orchestration) ➜
   shared Extractors (object-kind-specific dispatch) ➜ per-plugin
   `VendorMetadataQueries` (the catalog SQL).** Plugins own only the
   dialect-specific SQL + the per-row enrichment behaviour declared
   via `BaseQuirks` hooks; everything else is shared.

## Decision outcome

Chosen option: **3 — three-layer architecture**.

### Layer 1 — `SchemaIntrospector` (orchestration)

Located at `db/introspection/schema_introspector.py`. Owns the
shared `get_X()` entry-point methods. Each method:

1. Capability gate: short-circuit to `[]` if
   `vendor_queries.supports_X()` is false (no extractor
   instantiation, no connection opened).
2. Delegate to the matching extractor via a private getter
   (`_get_misc_extractor`, `_get_table_extractor`, ...).
3. Optional dialect-specific post-processing via quirks hook.

Plugin introspectors are no longer needed for the five SQL dialects
(MySQL, PostgreSQL, Oracle, SQL Server, DB2) — `IntrospectorFactory`
returns a `SchemaIntrospector(provider)` directly. SQLite (Python
native) and CosmosDB (NoSQL) keep their own
`<Dialect>Introspector(BaseIntrospector)` because their extractors
diverge from relational catalog introspection.

### Layer 2 — Extractors (`db/introspection/extractors/`)

One module per logical object kind: `TableExtractor`,
`ColumnExtractor`, `ConstraintExtractor`, `IndexExtractor`,
`ViewExtractor`, `SequenceExtractor`, `TriggerExtractor`,
`ProcedureExtractor`, `MiscExtractor`.

Each extractor:

- Calls `vendor_queries.get_<kind>_query(schema, ...)`.
- Iterates the result rows, builds the corresponding
  `core.sql_model.X` instance.
- Owns dialect-specific row decoding only when the catalog shape
  differs across dialects in a way the query alone can't normalise
  (e.g. trigger event bit-fields in PostgreSQL vs string lists in
  MySQL). These branches are progressively migrating to
  `BaseQuirks` hooks (post-F.3 cleanup wave H.2).

### Layer 3 — Per-plugin `VendorMetadataQueries`

Located at `db/introspection/databases/<dialect>/<dialect>_queries.py`.
Each subclass of `VendorMetadataQueries` (in
`db/introspection/vendor_queries_base.py`) owns:

- The catalog SQL strings (e.g. `SELECT … FROM information_schema.X`
  for PostgreSQL, `SELECT … FROM ALL_X` for Oracle).
- Capability flags: `supports_synonyms()`, `supports_packages()`,
  `supports_database_links()`, etc. Default in the base class is
  `False`; plugins override to `True` when the catalog supports
  the introspection.

`VendorQueriesFactory` resolves the right class through
`ProviderRegistry.get_quirks(dialect).vendor_queries_class()` — no
hardcoded registry in `core/` or `db/introspection/`.

### `BaseQuirks` introspection hooks

Per-dialect introspection behaviour that doesn't fit cleanly in a
catalog query lives on the plugin's quirks. Currently:

- `apply_vendor_table_properties(table, row)` — post-catalog-row
  enrichment (filegroup, tablespace, compression, storage_engine,
  ...).
- `extract_sqlplus_context`, `apply_sqlplus_preprocessing`,
  `parse_sqlplus_whenever`, `is_sqlplus_command`,
  `is_batch_separator_line`, `enable_server_message_capture`,
  `read_server_messages` — script-execution side hooks consumed by
  the migration engine, not introspection, but they live on the
  same `BaseQuirks` interface for consistency.

### Layering contract (enforced in CI)

`tests/unit/test_plugin_isolation.py` parses every `.py` file under
`core/`, `db/introspection/`, and `db/plugins/` with `ast` and asserts:

1. **No `core/` → plugin imports.** Core talks to plugins through
   `BaseQuirks` hooks and the registry factories
   (`SqlGeneratorFactory`, `IntrospectorFactory`,
   `VendorQueriesFactory`). Adding a new dialect requires no edit
   under `core/`.
2. **No `db/introspection/` → `core/{validation,licensing,migration}`
   leaks.** The only legal upward refs are `core.sql_model`,
   `core.logger`, `core.constants`.
3. **No cross-plugin imports** (except documented family
   inheritances: MariaDB ⊃ MySQL, CosmosDB parser ⊃ SQL Server
   parser).

A `KNOWN_VIOLATIONS` dict carries documented exemptions with a
follow-up reference; a companion test fails when an entry becomes
stale, so the allow-list stays in sync.

### Positive consequences

- **Plugin isolation strict.** Adding a new dialect is one folder
  (`db/plugins/<X>/` + `db/introspection/databases/<X>/`) plus an
  entry-point registration. The CI layering test fails any patch
  that violates this.
- **−2623 net LOC** across the F.3 + cleanup wave (~14 PRs).
- **Per-dialect SQL co-located** with its quirks, capability flags,
  and helpers. A debugging session for "why does Oracle return weird
  partition bounds" lands in one folder.
- **Capability gates everywhere.** `get_extensions()` on DB2 returns
  `[]` instantly — no provider roundtrip.
- **Two-source-of-truth bugs eliminated.** Oracle helpers exist
  exactly once (`_oracle_utils`); `VendorPropertyApplier` dispatch
  exists exactly once (per-plugin quirks override).

### Negative consequences

- **`SchemaIntrospector` still carries ~1100 LOC** of orchestration —
  smaller than the original 1843 but not yet split into focused
  modules. A future PR (Wave I.1) will decompose the column-enricher
  / partition-enricher / `introspect_schema` orchestrator into
  dedicated files.
- **Extractor-level dialect branches still exist** (procedure,
  constraint, index extractors have 8–16 each). These are scheduled
  to migrate to `BaseQuirks` hooks in Wave H.2 but the work is too
  large for the F.3 timeline.
- **CosmosDB introspection remains parallel.** It's a NoSQL plugin;
  the SchemaIntrospector ➜ extractor ➜
  VendorMetadataQueries pattern doesn't fit. Wave I.2 considers
  whether a `NoSQLIntrospector` intermediate base class would help
  or just add ceremony.

## Implementation reference

The architecture was implemented incrementally through these PRs:

- **F-series (foundation)**: layering test, hook plumbing, Rule 1 +
  Rule 2 strict. PRs #372 + #373 + #374.
- **F.3.a (inheritance pattern)**: PR #375. −2502 LOC.
- **Post-F.3 cleanup ("gros ménage")**: PRs #376 (Oracle utils),
  #377 (4 supports_X flags), #378 (PG triggers via shared path),
  #379 (drop 5 empty introspector subclasses), #380 (drop
  back-compat re-exports), #381 (`VendorPropertyApplier` via
  quirks), #382 + #383 (flaky tests + Bugbot follow-up), #384
  (CHANGELOG), and this ADR.

## Links

- ADR 0007 — Dialect capabilities matrix (data-only precursor)
- ADR 0026 — Dialect plugin isolation (DialectQuirks boundary)
- ADR 0027 — Generator isolation (the parallel DDL-side refactor)
- `docs/architecture/database-providers.md` § "Layering contract"
- `tests/unit/test_plugin_isolation.py` — the CI gate
